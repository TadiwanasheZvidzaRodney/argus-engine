terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  backend "s3" {
    bucket         = "argus-tfstate-prod"
    key            = "environment/prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "argus-tflocks-prod"
    encrypt        = true
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "argus-engine"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

module "vpc" {
  source      = "../../modules/vpc"
  environment = "prod"
  vpc_cidr    = "10.30.0.0/16"
}

module "security" {
  source      = "../../modules/security"
  environment = "prod"
}

module "data" {
  source             = "../../modules/data"
  environment        = "prod"
  vpc_id             = module.vpc.vpc_id
  data_subnet_ids    = module.vpc.data_subnet_ids
  app_kms_key_arn    = module.security.app_kms_key_arn
  audit_kms_key_arn  = module.security.audit_kms_key_arn
}

module "compute" {
  source                 = "../../modules/compute"
  environment            = "prod"
  vpc_id                 = module.vpc.vpc_id
  public_subnet_ids      = module.vpc.public_subnet_ids
  app_subnet_ids         = module.vpc.app_subnet_ids
  ecs_execution_role_arn = module.security.ecs_execution_role_arn
  ecs_task_role_arn      = module.security.ecs_task_role_arn
}

output "alb_dns_name" {
  value = module.compute.alb_dns_name
}
