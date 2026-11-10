terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

variable "environment" {
  type        = string
  description = "Environment name (dev, staging, prod)"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC"
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "Availability zones for subnet allocation"
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# --- VPC ---
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "argus-vpc-${var.environment}"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# --- Public Subnets (ALB & NAT Gateways) ---
resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name        = "argus-public-${var.availability_zones[count.index]}-${var.environment}"
    Type        = "public"
    Environment = var.environment
  }
}

# --- Private Application Subnets (ECS Tasks) ---
resource "aws_subnet" "app_private" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 4)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name        = "argus-app-private-${var.availability_zones[count.index]}-${var.environment}"
    Type        = "app-private"
    Environment = var.environment
  }
}

# --- Isolated Data Subnets (Aurora & ElastiCache) ---
resource "aws_subnet" "data_isolated" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 8)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name        = "argus-data-isolated-${var.availability_zones[count.index]}-${var.environment}"
    Type        = "data-isolated"
    Environment = var.environment
  }
}

# --- Internet Gateway ---
resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "argus-igw-${var.environment}"
    Environment = var.environment
  }
}

# --- NAT Gateway (Single NAT in dev, Multi-AZ in prod) ---
resource "aws_eip" "nat" {
  count  = var.environment == "prod" ? length(var.availability_zones) : 1
  domain = "vpc"

  tags = {
    Name        = "argus-nat-eip-${count.index}-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_nat_gateway" "nat" {
  count         = var.environment == "prod" ? length(var.availability_zones) : 1
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name        = "argus-nat-${count.index}-${var.environment}"
    Environment = var.environment
  }

  depends_on = [aws_internet_gateway.gw]
}

# --- Routing ---
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name        = "argus-rt-public-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "public" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "app_private" {
  count  = length(var.availability_zones)
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = var.environment == "prod" ? aws_nat_gateway.nat[count.index].id : aws_nat_gateway.nat[0].id
  }

  tags = {
    Name        = "argus-rt-app-${var.availability_zones[count.index]}-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "app_private" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.app_private[count.index].id
  route_table_id = aws_route_table.app_private[count.index].id
}

resource "aws_route_table" "data_isolated" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "argus-rt-data-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "data_isolated" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.data_isolated[count.index].id
  route_table_id = aws_route_table.data_isolated.id
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "app_subnet_ids" {
  value = aws_subnet.app_private[*].id
}

output "data_subnet_ids" {
  value = aws_subnet.data_isolated[*].id
}
