**IT infra monitoring AI agents**
*This project aims two goals*
1. Simplify IT infrastructure monitoring by gathering data and providing the health summary for me in Telegram
2. Learn how to build AI agents with LangGraph orchestration

*IT infrastructure to monitor*
1. EC2 instances: CPU, RAM, available HDD space 
2. Docker containers on this EC2 servers: running or not, health checks if available
3. API endpoints (FastAPI) health check
4. PostgreSQL Database availability and statistics from the table
5. LLM models availability: deployed in Azure AI cloud and Amazon Bedrock
6. Virtual servers with Ubuntu running docker containers 
7. S3 bucket statistics: number of created files this day, this week, this month - compared with the previous period; disk space usage

*Reporting*
I would like to get the summary report message with red/yellow/green lamps via Telegram and being able to dig into details if something went wrong.