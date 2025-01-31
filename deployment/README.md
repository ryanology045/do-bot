# ECS Deployment Notes

1. In `ecs_task_definition.json`, we have:
   - `executionRoleArn` = "arn:aws:iam::123456789012:role/EcsTaskExecutionRole"
   - `taskRoleArn` = "arn:aws:iam::123456789012:role/EcsTaskRole"
   Replace these with your real role ARNs.  

2. **GitHub Secrets**:  
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`  
   - `ECR_REPO_URI`, `ECS_CLUSTER`, `ECS_SERVICE`, `ECS_TASK_DEFINITION`  
   - `OPENAI_API_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, etc.  
   The pipeline replaces `<PLACEHOLDERS>` in the JSON with those values via `sed`.

3. **Push** to `main`. GitHub Actions builds & pushes your Docker image, updates the ECS task definition, and restarts the service.

4. **Slack**: Point your Slack App’s Event Subscriptions to `https://YOUR-LB-DOMAIN/slack/events`. Provide the same `SLACK_SIGNING_SECRET`.

You’re good to go!
