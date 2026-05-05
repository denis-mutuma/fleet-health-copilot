locals {
  single_instance_enabled = var.enable_single_instance
  single_instance_secret_arns = distinct(concat(
    values(local.managed_web_secret_arns),
    values(local.managed_orchestrator_secret_arns),
    values(var.web_secret_arns),
    values(var.orchestrator_secret_arns),
  ))
  single_instance_secret_access_enabled = local.single_instance_enabled && length(local.single_instance_secret_arns) > 0
}

data "aws_ami" "amazon_linux_2023" {
  count = local.single_instance_enabled ? 1 : 0

  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-kernel-6.1-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  count = local.single_instance_enabled ? 1 : 0

  name = "com.amazonaws.global.cloudfront.origin-facing"
}

data "aws_iam_policy_document" "single_instance_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "single_instance_runtime" {
  count = local.single_instance_enabled ? 1 : 0

  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    effect    = "Allow"
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer"
    ]
    effect    = "Allow"
    resources = [for repository in aws_ecr_repository.service : repository.arn]
  }
}

data "aws_iam_policy_document" "single_instance_secret_access" {
  count = local.single_instance_secret_access_enabled ? 1 : 0

  statement {
    actions = [
      "secretsmanager:GetSecretValue",
      "ssm:GetParameters"
    ]
    effect    = "Allow"
    resources = local.single_instance_secret_arns
  }
}

resource "aws_iam_role" "single_instance" {
  count = local.single_instance_enabled ? 1 : 0

  name               = "${local.name_prefix}-single-instance"
  assume_role_policy = data.aws_iam_policy_document.single_instance_assume_role.json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "single_instance_ssm" {
  count = local.single_instance_enabled ? 1 : 0

  role       = aws_iam_role.single_instance[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "single_instance_runtime" {
  count = local.single_instance_enabled ? 1 : 0

  name   = "${local.name_prefix}-single-instance-runtime"
  role   = aws_iam_role.single_instance[0].id
  policy = data.aws_iam_policy_document.single_instance_runtime[0].json
}

resource "aws_iam_role_policy" "single_instance_secret_access" {
  count = local.single_instance_secret_access_enabled ? 1 : 0

  name   = "${local.name_prefix}-single-instance-secrets"
  role   = aws_iam_role.single_instance[0].id
  policy = data.aws_iam_policy_document.single_instance_secret_access[0].json
}

resource "aws_iam_instance_profile" "single_instance" {
  count = local.single_instance_enabled ? 1 : 0

  name = "${local.name_prefix}-single-instance"
  role = aws_iam_role.single_instance[0].name

  tags = local.common_tags
}

resource "aws_security_group" "single_instance" {
  count = local.single_instance_enabled ? 1 : 0

  name        = "${local.name_prefix}-single-instance"
  description = "Allow HTTP from CloudFront to the single-instance web runtime."
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTP from CloudFront origin-facing edge locations"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront_origin_facing[0].id]
  }

  egress {
    description = "Outbound application, ECR, and SSM traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_eip" "single_instance" {
  count = local.single_instance_enabled ? 1 : 0

  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-single-instance"
  })
}

resource "aws_instance" "single_instance" {
  count = local.single_instance_enabled ? 1 : 0

  ami                         = data.aws_ami.amazon_linux_2023[0].id
  instance_type               = var.single_instance_type
  subnet_id                   = var.public_subnet_ids[0]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.single_instance[0].name
  vpc_security_group_ids      = [aws_security_group.single_instance[0].id]

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 12
  }

  ebs_block_device {
    device_name           = "/dev/sdf"
    delete_on_termination = false
    encrypted             = true
    volume_size           = var.single_instance_volume_size
    volume_type           = "gp3"
    tags = merge(local.common_tags, {
      Name = "${local.name_prefix}-single-instance-data"
    })
  }

  user_data_replace_on_change = false
  user_data                   = file("${path.module}/templates/single-instance-user-data.sh.tftpl")

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-single-instance"
  })

  depends_on = [
    aws_iam_role_policy_attachment.single_instance_ssm,
    aws_iam_role_policy.single_instance_runtime
  ]
}

resource "aws_eip_association" "single_instance" {
  count = local.single_instance_enabled ? 1 : 0

  allocation_id = aws_eip.single_instance[0].id
  instance_id   = aws_instance.single_instance[0].id
}
