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

# --- KMS Customer Managed Keys ---
resource "aws_kms_key" "app_data" {
  description             = "Argus Engine application data key (${var.environment})"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Name        = "argus-kms-app-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "app_data" {
  name          = "alias/argus-app-${var.environment}"
  target_key_id = aws_kms_key.app_data.key_id
}

resource "aws_kms_key" "audit_archive" {
  description             = "Argus Engine audit archive encryption key (${var.environment})"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Name        = "argus-kms-audit-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "audit_archive" {
  name          = "alias/argus-audit-${var.environment}"
  target_key_id = aws_kms_key.audit_archive.key_id
}

# --- ECS Task Execution Role ---
resource "aws_iam_role" "ecs_execution_role" {
  name = "argus-ecs-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# --- ECS Task Application Role ---
resource "aws_iam_role" "ecs_task_role" {
  name = "argus-ecs-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "ecs_task_policy" {
  name = "argus-ecs-task-policy-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSAccess"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = [
          aws_kms_key.app_data.arn,
          aws_kms_key.audit_archive.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_task_policy.arn
}

output "app_kms_key_arn" {
  value = aws_kms_key.app_data.arn
}

output "audit_kms_key_arn" {
  value = aws_kms_key.audit_archive.arn
}

output "ecs_execution_role_arn" {
  value = aws_iam_role.ecs_execution_role.arn
}

output "ecs_task_role_arn" {
  value = aws_iam_role.ecs_task_role.arn
}
