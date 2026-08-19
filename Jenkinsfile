pipeline {
  agent any

  environment {
    AWS_REGION = "us-east-1"            // override as needed
    ECR_REPO = "my-flask-app"           // ECR repo name (create in AWS ECR beforehand)
    RECIPIENTS = "dev-team@example.com" // email recipients for notifications
    APP_PORT = "5000"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
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
        // Run pytest; any failure will abort the pipeline automatically
        sh 'pytest -q'
      }
    }

    stage('Build') {
      steps {
        script {
          // Determine commit SHA (short)
          COMMIT_SHORT = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          IMAGE_LOCAL = "${ECR_REPO}:${COMMIT_SHORT}"
          sh "docker build -t ${IMAGE_LOCAL} ."
        }
      }
    }

    stage('Push to ECR') {
      steps {
        // AWS credentials required: configure as Jenkins credentials (username/password style or access keys)
        withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
          script {
            // Ensure repository URI
            ACCOUNT_ID = sh(script: "aws sts get-caller-identity --query Account --output text", returnStdout: true).trim()
            ECR_URI = "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
            // Login to ECR
            sh "aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}"
            // Create repo if not exists (idempotent if repo exists)
            sh "aws ecr describe-repositories --region ${AWS_REGION} --repository-names ${ECR_REPO} || aws ecr create-repository --region ${AWS_REGION} --repository-name ${ECR_REPO}"
            // Tag and push
            COMMIT_SHORT = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
            IMAGE_LOCAL = "${ECR_REPO}:${COMMIT_SHORT}"
            IMAGE_REMOTE = "${ECR_URI}:${COMMIT_SHORT}"
            sh "docker tag ${IMAGE_LOCAL} ${IMAGE_REMOTE}"
            sh "docker push ${IMAGE_REMOTE}"
          }
        }
      }
    }

    stage('Deploy to EC2') {
      environment {
        // Set these as Jenkins credentials/parameters in your job
        EC2_USER = "ec2-user"
        EC2_HOST = "ec2-host.example.com"
        SSH_CREDENTIALS_ID = "ec2-ssh-key" // Jenkins SSH private key credential id
      }
      steps {
        script {
          COMMIT_SHORT = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          IMAGE_REMOTE = sh(script: "aws sts get-caller-identity --query Account --output text --output text | awk '{print $1}'", returnStdout: true).trim() + ".dkr.ecr." + AWS_REGION + ".amazonaws.com/${ECR_REPO}:${COMMIT_SHORT}"

          // Use SSH private key stored in Jenkins credentials
          withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CREDENTIALS_ID, keyFileVariable: 'PEM', usernameVariable: 'SSH_USER')]) {
            // Commands to run on EC2 to deploy the new container
            def remoteCmds = """
              set -e
              # Ensure docker is installed on the EC2 instance
              docker pull ${IMAGE_REMOTE}
              # Stop and remove any running container named app
              if [ \$(docker ps -aq -f name=app) ]; then
                docker stop app || true
                docker rm app || true
              fi
              # Run new container
              docker run -d --name app -p ${APP_PORT}:5000 ${IMAGE_REMOTE}
              # Wait a bit for app to initialize
              sleep 5
              # Check health endpoint locally on the instance
              HTTP_CODE=\$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${APP_PORT}/health || echo "000")
              if [ "${HTTP_CODE}" != "200" ]; then
                echo "Health check failed with status ${HTTP_CODE}"
                exit 1
              fi
            """

            // Execute remote commands via ssh
            sh "scp -o StrictHostKeyChecking=no -i $PEM /dev/null ${SSH_USER}@${EC2_HOST}:/tmp/jenkins_touch || true"
            sh "ssh -o StrictHostKeyChecking=no -i $PEM ${SSH_USER}@${EC2_HOST} '${remoteCmds}'"
          }
        }
      }
    }

    stage('Verify from Pipeline') {
      steps {
        script {
          COMMIT_SHORT = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          IMAGE_REMOTE = sh(script: "aws sts get-caller-identity --query Account --output text", returnStdout: true).trim() + ".dkr.ecr." + AWS_REGION + ".amazonaws.com/${ECR_REPO}:${COMMIT_SHORT}"
          // Verify the public/endpoint health — adjust to use instance public IP or load balancer DNS
          sh "curl --fail -sS http://${EC2_HOST}:${APP_PORT}/health"
        }
      }
    }
  }

  post {
    success {
      mail to: "${RECIPIENTS}", subject: "SUCCESS: Job ${env.JOB_NAME} [${env.BUILD_NUMBER}]", body: "Build and deploy succeeded. Image: ${ECR_REPO}:${env.GIT_COMMIT ?: 'unknown'}"
    }
    failure {
      mail to: "${RECIPIENTS}", subject: "FAILURE: Job ${env.JOB_NAME} [${env.BUILD_NUMBER}]", body: "Build or deploy FAILED. See console output: ${env.BUILD_URL}"
    }
    unstable {
      mail to: "${RECIPIENTS}", subject: "UNSTABLE: Job ${env.JOB_NAME} [${env.BUILD_NUMBER}]", body: "Build unstable. See console output: ${env.BUILD_URL}"
    }
    always {
      // Archive Docker image id or similar artifacts if desired
    }
  }
}
