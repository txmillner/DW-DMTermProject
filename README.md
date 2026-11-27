# DW-DMTermProject

Census Data API User Guide
https://www2.census.gov/api-documentation/api-user-guide.pdf


docker run -d \
  -e POSTGRES_USER=txmillner \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=warehouse \
  -p 5432:5432 \
  --name warehouse-db \
  postgres:15

docker exec -i warehouse-db psql -U txmillner -d warehouse < src/schema.sql
