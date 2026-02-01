---
name: "devops-guide"
description: "Handles deployment, Docker configuration, Git workflows, and migration tasks. Invoke when user asks about deployment, CI/CD, servers, or git."
---

# DevOps & Deployment Guide

This skill provides context and guidelines for the project's deployment and DevOps workflows.

## Reference Documentation

The following documentation files in `docs/devops/` are the source of truth for this skill:

- [DEPLOYMENT_WORKFLOW.md](file:///root/zzp/langextract-main/generate_report_test/docs/devops/DEPLOYMENT_WORKFLOW.md): Detailed deployment workflow using Docker and Git Tags.
- [DOCKER_DEPLOY_PLAN.md](file:///root/zzp/langextract-main/generate_report_test/docs/devops/DOCKER_DEPLOY_PLAN.md): Plans and specifications for Docker deployment.
- [GIT_GUIDE.md](file:///root/zzp/langextract-main/generate_report_test/docs/devops/GIT_GUIDE.md): Git usage guidelines.
- [MIGRATION_PLAN.md](file:///root/zzp/langextract-main/generate_report_test/docs/devops/MIGRATION_PLAN.md): Database and system migration plans.
- [public_repo_integration_plan.md](file:///root/zzp/langextract-main/generate_report_test/docs/devops/public_repo_integration_plan.md): Integration with public repositories.

## Key Workflows

### Deployment
Run `./deploy.sh` to commit, tag, and push changes for production deployment.

### Development
Run `./start-dev.sh` to start the local development environment.
