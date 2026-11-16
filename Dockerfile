FROM python:3.10-slim
RUN apt-get update && apt-get install -y nodejs npm curl
RUN npm install -g snarkjs
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN ls -la
EXPOSE 5000
CMD ["python", "main.py"]
