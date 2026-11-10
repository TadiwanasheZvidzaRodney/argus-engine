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

variable "public_subnet_ids" {
  type = list(string)
}

variable "app_subnet_ids" {
  type = list(string)
}

variable "ecs_execution_role_arn" {
  type = string
}

variable "ecs_task_role_arn" {
  type = string
}

# --- ECS Cluster ---
resource "aws_ecs_cluster" "main" {
  name = "argus-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name        = "argus-cluster-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = var.environment == "prod" ? "FARGATE" : "FARGATE_SPOT"
  }
}

# --- CloudWatch Log Group ---
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/argus-${var.environment}"
  retention_in_days = var.environment == "prod" ? 90 : 14

  tags = {
    Environment = var.environment
  }
}

# --- Security Groups ---
resource "aws_security_group" "alb" {
  name        = "argus-alb-sg-${var.environment}"
  description = "Public ALB ingress"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP ingress"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS ingress"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "argus-alb-sg-${var.environment}"
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "argus-tasks-sg-${var.environment}"
  description = "Ingress to ECS tasks from ALB"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Traffic from ALB"
    from_port       = 8000
    to_port         = 8001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "argus-tasks-sg-${var.environment}"
  }
}

# --- Application Load Balancer ---
resource "aws_lb" "main" {
  name               = "argus-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  drop_invalid_header_fields = true

  tags = {
    Name        = "argus-alb-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "api" {
  name        = "argus-tg-api-${var.environment}"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/healthz"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name = "argus-tg-api-${var.environment}"
  }
}

resource "aws_lb_target_group" "ws" {
  name        = "argus-tg-ws-${var.environment}"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/healthz"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name = "argus-tg-ws-${var.environment}"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener_rule" "ws" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ws.arn
  }

  condition {
    path_pattern {
      values = ["/ws/*"]
    }
  }
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "ecs_cluster_id" {
  value = aws_ecs_cluster.main.id
}
