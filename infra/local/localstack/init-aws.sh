#!/usr/bin/env bash
# Provision the local AWS surface Argus needs from Phase 1 onward.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"

awslocal s3api create-bucket --bucket argus-audit-local --region "$REGION" >/dev/null 2>&1 || true
awslocal s3api put-bucket-versioning --bucket argus-audit-local \
  --versioning-configuration Status=Enabled
awslocal s3api create-bucket --bucket argus-raw-payloads-local --region "$REGION" >/dev/null 2>&1 || true
awslocal s3api create-bucket --bucket argus-frontend-local --region "$REGION" >/dev/null 2>&1 || true

awslocal sqs create-queue --queue-name argus-events-dlq >/dev/null 2>&1 || true
DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url "$(awslocal sqs get-queue-url --queue-name argus-events-dlq --query QueueUrl --output text)" \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
awslocal sqs create-queue --queue-name argus-events \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}" \
  >/dev/null 2>&1 || true

awslocal events create-event-bus --name argus-events >/dev/null 2>&1 || true

awslocal kms create-key --description "argus-local application data" \
  --query KeyMetadata.KeyId --output text >/dev/null

echo "localstack: argus resources provisioned"
