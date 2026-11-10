# Spike P0-34: STS + CloudFormation Onboarding

## 1. Objective
Validate cross-account IAM role assumption via AWS STS, verify that `ExternalId` prevents the Confused Deputy problem, and confirm that an inline scope-down session policy successfully restricts Argus operations to the specific tenant session.

## 2. Key Findings

1. **ExternalId Enforcement:**
   - Every tenant is provisioned with a dedicated cryptographically secure `ExternalId` (`tnt_<uuidv7>:<random_token>`).
   - The CloudFormation stack deployed into customer accounts creates `ArgusExecutionRole` with:
     ```json
     {
       "Effect": "Allow",
       "Principal": { "AWS": "arn:aws:iam::111122223333:role/argus-worker-prod" },
       "Action": "sts:AssumeRole",
       "Condition": {
         "StringEquals": { "sts:ExternalId": "tnt_0190c3a1-0000-7000-8000-000000000001:sec_abc123" }
       }
     }
     ```
   - Attempting to assume the role with any other ExternalId fails immediately with `AccessDenied`.

2. **Session Policies for Read-Only vs Action Scopes:**
   - During periodic discovery, Argus passes a read-only session policy to `AssumeRole`:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [{
         "Effect": "Allow",
         "Action": ["*Explorer*", "*Describe*", "*Get*", "*List*"],
         "Resource": "*"
       }]
     }
     ```
   - During Phase 6 action execution, the session policy is narrowed exclusively to the exact target ARN and action approved in the immutable action plan.

3. **Duration:**
   - Discovery sessions are capped at 1 hour.
   - Action execution sessions are capped at 15 minutes.
