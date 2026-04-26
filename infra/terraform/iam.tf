locals {
  # When we do not create the provider in this workspace, use the well-known ARN shape for GitHub's
  # OIDC URL (no iam:GetOpenIDConnectProvider — the deploy role often lacks that read permission).
  github_oidc_provider_arn = !local.github_oidc_enabled ? "" : (
    var.manage_github_oidc_provider
    ? aws_iam_openid_connect_provider.github_actions[0].arn
    : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
  )
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  count = local.github_oidc_enabled ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:*"]
    }
  }
}

data "aws_iam_policy_document" "github_actions_ecr" {
  count = local.github_oidc_enabled ? 1 : 0

  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    effect    = "Allow"
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart"
    ]
    effect    = "Allow"
    resources = [for repository in aws_ecr_repository.service : repository.arn]
  }
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  count = local.github_oidc_enabled && var.manage_github_oidc_provider ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = local.common_tags
}

resource "aws_iam_role" "github_actions" {
  count = local.github_oidc_enabled ? 1 : 0

  name               = "${local.name_prefix}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role[0].json

  tags = local.common_tags
}

resource "aws_iam_role_policy" "github_actions_ecr" {
  count = local.github_oidc_enabled ? 1 : 0

  name   = "${local.name_prefix}-github-actions-ecr"
  role   = aws_iam_role.github_actions[0].id
  policy = data.aws_iam_policy_document.github_actions_ecr[0].json
}

# GitHub-driven terraform apply needs broad IAM unless you replace this with a custom policy.
resource "aws_iam_role_policy_attachment" "github_actions_administrator" {
  count = local.github_oidc_enabled && var.github_actions_attach_administrator_access ? 1 : 0

  role       = aws_iam_role.github_actions[0].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
