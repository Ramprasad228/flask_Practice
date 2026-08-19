pipeline {
  agent any

  environment {
    AWS_REGION = "us-east-1"
    ECR_REPO = "my-flask-app"
    APP_PORT = "5000"
    EC2_USER = "ec2-user"
    EC2_PUBLIC_IP = "44.222.88.24"
    SSH_CREDENTIALS_ID = "ec2-ssh-key"
    RECIPIENTS = "ramprasadk257@gmail.com"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Prepare .env from Jenkins secrets') {
      steps {
        withCredentials([
          string(credentialsId: 'mongo-uri', variable: 'MONGO_URI'),
          string(credentialsId: 'secret-key', variable: 'SECRET_KEY')
        ]) {
          sh '''
            set -e
            printf '%s\n%s\n' "MONGO_URI=${MONGO_URI}" "SECRET_KEY=${SECRET_KEY}" > .env
            echo "Generated .env file from Jenkins credentials"
          '''
        }
      }
    }

    stage('Install dependencies') {
      steps {
        sh 'python -m pip install --upgrade pip'
        sh 'pip install -r requirements.txt'
      }
    }

    stage('Test') {
      steps {
        sh 'python -m pytest -q'
      }
    }

    stage('Build Docker image') {
      steps {
        script {
          COMMIT_SHA = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          IMAGE_LOCAL = "${ECR_REPO}:${COMMIT_SHA}"
          sh "docker build -t ${IMAGE_LOCAL} ."
          env.COMMIT_SHA = COMMIT_SHA
        }
      }
    }

    stage('Push to ECR') {
      steps {
        withCredentials([
          [$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']
        ]) {
          script {
            ACCOUNT_ID = sh(script: "aws sts get-caller-identity --query Account --output text", returnStdout: true).trim()
            ECR_URI = "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
            env.ECR_URI = ECR_URI
            sh "aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}"
            sh "aws ecr describe-repositories --region ${AWS_REGION} --repository-names ${ECR_REPO} || aws ecr create-repository --region ${AWS_REGION} --repository-name ${ECR_REPO}"
            IMAGE_REMOTE = "${ECR_URI}:${env.COMMIT_SHA}"
            sh "docker tag ${ECR_REPO}:${env.COMMIT_SHA} ${IMAGE_REMOTE}"
            sh "docker push ${IMAGE_REMOTE}"
          }
        }
      }
    }

    stage('Deploy to EC2') {
      steps {
        withCredentials([
          sshUserPrivateKey(credentialsId: env.SSH_CREDENTIALS_ID, keyFileVariable: 'PEM', usernameVariable: 'SSH_USER'),
          string(credentialsId: 'mongo-uri', variable: 'MONGO_URI'),
          string(credentialsId: 'secret-key', variable: 'SECRET_KEY')
        ]) {
          script {
            IMAGE_REMOTE = "${env.ECR_URI}:${env.COMMIT_SHA}"
            def remoteCmds = """
              set -e
              docker pull mongo:latest
              docker pull python:3.11-slim
              docker rm -f mongo_app app || true
              docker network inspect app-network >/dev/null 2>&1 || docker network create app-network

              docker run -d --name mongo_app --network app-network -p 27017:27017 -v mongo_data:/data/db mongo:latest
              sleep 10

              docker pull ${IMAGE_REMOTE}
              docker run -d --name app --network app-network -p ${APP_PORT}:5000 \\
                -e MONGO_URI='mongodb://mongo_app:27017/student_db' \\
                -e SECRET_KEY='${SECRET_KEY}' \\
                ${IMAGE_REMOTE}

              for i in \$(seq 1 30); do
                HTTP_CODE=\$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${APP_PORT}/health || echo 000)
                if [ \"\$HTTP_CODE\" = \"200\" ]; then
                  echo \"App health check passed\"
                  exit 0
                fi
                sleep 2
              done

              echo \"App did not become healthy\"
              exit 1
            """

            sh "ssh -o StrictHostKeyChecking=no -i \"$PEM\" ${SSH_USER}@${EC2_PUBLIC_IP} '${remoteCmds}'"
          }
        }
      }
    }

    stage('Verify via EC2 public IP') {
      steps {
        sh "curl --fail --silent --show-error http://${EC2_PUBLIC_IP}:${APP_PORT}/health"
      }
    }
  }

  post {
    success {
      mail to: "${RECIPIENTS}", subject: "SUCCESS: Job ${env.JOB_NAME} [${env.BUILD_NUMBER}]", body: "Deployment succeeded. Image: ${env.ECR_URI}:${env.COMMIT_SHA}"
    }
    failure {
      mail to: "${RECIPIENTS}", subject: "FAILURE: Job ${env.JOB_NAME} [${env.BUILD_NUMBER}]", body: "Build or deployment failed. Console output: ${env.BUILD_URL}"
    }
    unstable {
      mail to: "${RECIPIENTS}", subject: "UNSTABLE: Job ${env.JOB_NAME} [${env.BUILD_NUMBER}]", body: "Build is unstable. Console output: ${env.BUILD_URL}"
    }
    always {
      sh 'rm -f .env'
    }
  }
}
