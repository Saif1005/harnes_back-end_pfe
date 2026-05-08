# AWS Deployment (g4dn.xlarge)

Target instance details (provided):

- instance_id: `i-04a73e357a7343429`
- key_name: `saif_pipeline`
- key_path: `/home/saifakkari/PFE_Saif/saif_pipeline.pem`
- instance_type: `g4dn.xlarge`

## 1) One-command deployment

From `Back-end/projet_industriel_agi`:

```bash
./scripts/deploy_harness_to_instance.sh
```

This script:

1. resolves instance public IP from AWS using `instance_id`,
2. syncs project by `rsync` with existing exclude rules,
3. runs `docker compose -f docker-compose.harness.yml up -d --build` remotely.

## 2) Runtime architecture on EC2

- `harness-backend` on port `8030`
- `harness-mcp-server` on port `8040`
- backend communicates to MCP server via:
  - `MCP_ENABLED=true`
  - `MCP_SERVER_URL=http://harness-mcp-server:8040/mcp/tool-call`

## 3) Verification commands (remote)

```bash
docker ps
curl -s http://127.0.0.1:8030/health
curl -s http://127.0.0.1:8030/system/protocols
```

## 4) Training containers

Classification and prediction training Dockerfiles are in:

- `harness_backend/docker/training/Dockerfile.classification-train`
- `harness_backend/docker/training/Dockerfile.prediction-train`
- compose: `harness_backend/docker/training/docker-compose.training.yml`

