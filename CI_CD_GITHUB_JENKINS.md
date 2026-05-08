# CI/CD: GitHub Actions + Jenkins Monitoring

## GitHub Actions (deploy)

Workflow file:

- `.github/workflows/harness-ci-cd.yml`

### Required GitHub Secrets

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (example: `eu-west-3`)
- `EC2_INSTANCE_ID` (for your case: `i-04a73e357a7343429`)
- `EC2_SSH_PRIVATE_KEY` (content of `saif_pipeline.pem`)

### Behavior

1. CI on PR/main:
   - installs dependencies,
   - compiles backend modules,
   - runs smoke graph test.
2. Deploy on `main`:
   - resolves instance via AWS,
   - runs `scripts/deploy_harness_to_instance.sh`,
   - updates `docker-compose.harness.yml` stack remotely.

## Jenkins (monitoring)

Pipeline file:

- `Jenkinsfile`

Monitoring script:

- `scripts/monitor_harness_remote.sh`

### Required Jenkins Credentials

- `aws-access-key-id` (secret text)
- `aws-secret-access-key` (secret text)
- `aws-region` (secret text)
- `ec2-instance-id` (secret text)
- `saif-pipeline-pem` (secret file, your SSH private key)

### Checks executed

- `docker compose ... ps`
- `GET /health`
- `GET /system/protocols`
- `POST /mcp/tool-call` smoke probe

