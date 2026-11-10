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
  type = string
}

variable "vpc_id" {
  type = string
}

variable "data_subnet_ids" {
  type = list(string)
}

variable "app_kms_key_arn" {
  type = string
}

variable "audit_kms_key_arn" {
  type = string
}

# --- S3 Audit Archive (Object Lock Compliance) ---
resource "aws_s3_bucket" "audit_archive" {
  bucket        = "argus-audit-archive-${var.environment}"
  force_destroy = var.environment != "prod"

  object_lock_configuration {
    object_lock_enabled = "Enabled"
  }

  tags = {
    Name        = "argus-audit-archive-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.audit_kms_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "audit_archive" {
  bucket                  = aws_s3_bucket.audit_archive.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- S3 Raw Discovery Payloads ---
resource "aws_s3_bucket" "raw_payloads" {
  bucket        = "argus-raw-payloads-${var.environment}"
  force_destroy = var.environment != "prod"

  tags = {
    Name        = "argus-raw-payloads-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_payloads" {
  bucket = aws_s3_bucket.raw_payloads.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.app_kms_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "raw_payloads" {
  bucket                  = aws_s3_bucket.raw_payloads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- Aurora PostgreSQL Subnet Group & Security Group ---
resource "aws_db_subnet_group" "aurora" {
  name       = "argus-aurora-${var.environment}"
  subnet_ids = var.data_subnet_ids

  tags = {
    Name = "argus-aurora-subnet-group-${var.environment}"
  }
}

resource "aws_security_group" "aurora" {
  name        = "argus-aurora-sg-${var.environment}"
  description = "Access to Aurora from application tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "argus-aurora-sg-${var.environment}"
  }
}

# --- ElastiCache Redis Subnet Group & Security Group ---
resource "aws_elasticache_subnet_group" "redis" {
  name       = "argus-redis-${var.environment}"
  subnet_ids = var.data_subnet_ids
}

resource "aws_security_group" "redis" {
  name        = "argus-redis-sg-${var.environment}"
  description = "Access to Redis from application tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "argus-redis-sg-${var.environment}"
  }
}

output "audit_bucket_name" {
  value = aws_s3_bucket.audit_archive.id
}

output "raw_payloads_bucket_name" {
  value = aws_s3_bucket.raw_payloads.id
}

output "aurora_security_group_id" {
  value = aws_security_group.aurora.id
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}
