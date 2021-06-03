resource "aws_s3_bucket" "cf_asset_bucket" {
  bucket        = var.asset_bucket
  acl           = "private"
  force_destroy = true
  versioning {
    enabled = true
  }

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "aws:kms"
      }
    }
  }
}

resource "aws_s3_bucket_policy" "ssl_only" {
  bucket = aws_s3_bucket.cf_asset_bucket.id
  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "AccessControl"
    Statement = [{
      Sid       = "AllowSSLRequestsOnly"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.cf_asset_bucket.arn,
        "${aws_s3_bucket.cf_asset_bucket.arn}/*"
      ]
      Condition = {
        Bool = {
          "aws:SecureTransport" = false
        }
      }
    }]
  })
}

resource "aws_s3_bucket_public_access_block" "deny_public_access" {
  bucket                  = aws_s3_bucket.cf_asset_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  depends_on = [aws_s3_bucket_policy.ssl_only]
}

resource "aws_s3_bucket_object" "assets" {
  for_each = fileset("${var.asset_dir}/", "**")
  bucket   = aws_s3_bucket.cf_asset_bucket.id
  key      = each.value
  source   = "${var.asset_dir}/${each.value}"
  etag     = filemd5("${var.asset_dir}/${each.value}")
  depends_on = [
    aws_s3_bucket_public_access_block.deny_public_access
  ]
}
