pipeline {
  agent any

  parameters {
    string(name: 'AWS_REGION', defaultValue: 'us-east-1', description: 'AWS region for ECR and SSM execution.')
    string(name: 'ECR_REPO', defaultValue: 'my-flask-app', description: 'ECR repository name.')
    string(name: 'APP_PORT', defaultValue: '5000', description: 'Port exposed by the Flask app inside Docker.')
    string(name: 'EC2_INSTANCE_ID', defaultValue: '', description: 'EC2 instance ID. Must have SSM agent installed and an IAM instance profile with ECR/SSM permissions.')
    string(name: 'EC2_PUBLIC_IP', defaultValue: '', description: 'Public IP or DNS name of the EC2 instance used for final health verification.')
    string(name: 'MONGO_URI', defaultValue: 'mongodb://mongo_app:27017/student_db', description: 'MongoDB connection string used by the app inside EC2 network.')
    string(name: 'SECRET_KEY', defaultValue: '', description: 'Flask SECRET_KEY to inject into the app container.')
    string(name: 'MAIL_RECIPIENTS', defaultValue: 'dev-team@example.com', description: 'Email recipients for success/failure notifications.')
    string(name: 'AWS_CREDENTIAL_ID', defaultValue: '', description: 'Optional Jenkins AWS credential ID. Leave blank to use the Jenkins node/role IAM credentials instead.')
  }

  environment {
    AWS_REGION = "${params.AWS_REGION}"
    ECR_REPO = "${params.ECR_REPO}"
    APP_PORT = "${params.APP_PORT}"
    EC2_INSTANCE_ID = "${params.EC2_INSTANCE_ID}"
    EC2_PUBLIC_IP = "${params.EC2_PUBLIC_IP}"
    MONGO_URI = "${params.MONGO_URI}"
    SECRET_KEY = "${params.SECRET_KEY}"
    RECIPIENTS = "${params.MAIL_RECIPIENTS}"
    AWS_CREDENTIAL_ID = "${params.AWS_CREDENTIAL_ID}"
    COMMIT_SHA = ""
    ECR_URI = ""
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Prepare .env from runtime parameters') {
      steps {
        sh '''
          set -e
          if [ -z "$SECRET_KEY" ] || [ -z "$MONGO_URI" ]; then
            echo "SECRET_KEY and MONGO_URI must be passed as pipeline parameters."
            exit 1
          fi
          printf '%s\n%s\n' "MONGO_URI=$MONGO_URI" "SECRET_KEY=$SECRET_KEY" > .env
          echo "Generated .env file from runtime pipeline parameters"
        '''
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
        script {
          if (params.AWS_CREDENTIAL_ID?.trim()) {
            withCredentials([
              [$class: 'AmazonWebServicesCredentialsBinding',
               credentialsId: params.AWS_CREDENTIAL_ID,
               accessKeyVariable: 'AWS_ACCESS_KEY_ID',
               secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']
            ]) {
              pushToEcr()
            }
          } else {
            pushToEcr()
          }
        }
      }
    }

    stage('Deploy to EC2 via IAM + SSM') {
      steps {
        script {
          if (!params.EC2_INSTANCE_ID?.trim()) {
            error('EC2_INSTANCE_ID must be supplied when triggering the pipeline.')
          }
          if (!params.EC2_PUBLIC_IP?.trim()) {
            error('EC2_PUBLIC_IP must be supplied when triggering the pipeline.')
          }

          if (params.AWS_CREDENTIAL_ID?.trim()) {
            withCredentials([
              [$class: 'AmazonWebServicesCredentialsBinding',
               credentialsId: params.AWS_CREDENTIAL_ID,
               accessKeyVariable: 'AWS_ACCESS_KEY_ID',
               secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']
            ]) {
              deployToEc2ViaSsm()
            }
          } else {
            deployToEc2ViaSsm()
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

def pushToEcr() {
  ACCOUNT_ID = sh(script: "aws sts get-caller-identity --query Account --output text 2>/dev/null || true", returnStdout: true).trim()
  if (!ACCOUNT_ID) {
    error('AWS CLI is not authenticated. Configure Jenkins AWS credentials or attach an IAM role to the Jenkins agent before pushing to ECR.')
  }

  env.ECR_URI = "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

  sh "aws ecr describe-repositories --region ${AWS_REGION} --repository-names ${ECR_REPO} || aws ecr create-repository --region ${AWS_REGION} --repository-name ${ECR_REPO}"
  sh "aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${env.ECR_URI}"

  IMAGE_REMOTE = "${env.ECR_URI}:${env.COMMIT_SHA}"
  sh "docker tag ${ECR_REPO}:${env.COMMIT_SHA} ${IMAGE_REMOTE}"
  sh "docker push ${IMAGE_REMOTE}"
}

def deployToEc2ViaSsm() {
  if (!env.ECR_URI?.trim()) {
    error('ECR URI is empty. Ensure the ECR push stage completed successfully before deploying to EC2.')
  }

  IMAGE_REMOTE = "${env.ECR_URI}:${env.COMMIT_SHA}"

  def appCommands = [
    'set -e',
    'sudo systemctl enable --now docker 2>/dev/null || true',
    'sudo usermod -aG docker ec2-user 2>/dev/null || true',
    'aws ecr get-login-password --region ' + AWS_REGION + ' | sudo docker login --username AWS --password-stdin ' + env.ECR_URI,
    'sudo docker network inspect app-network >/dev/null 2>&1 || sudo docker network create app-network',
    'sudo docker rm -f mongo_app app || true',
    'sudo docker pull mongo:latest',
    'sudo docker run -d --name mongo_app --network app-network -p 27017:27017 -v mongo_data:/data/db mongo:latest',
    'sleep 10',
    'sudo docker pull ' + IMAGE_REMOTE,
    'sudo docker run -d --name app --network app-network -p ' + APP_PORT + ':5000 -e MONGO_URI=\'' + MONGO_URI + '\' -e SECRET_KEY=\'' + SECRET_KEY + '\' ' + IMAGE_REMOTE,
    'for i in $(seq 1 30); do HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:' + APP_PORT + '/health || echo 000); if [ "$HTTP_CODE" = "200" ]; then echo "App health check passed"; exit 0; fi; sleep 2; done; echo "App did not become healthy"; exit 1'
  ]

  def ssmJson = groovy.json.JsonOutput.toJson([commands: appCommands])

  def commandId = sh(script: "aws ssm send-command --region ${AWS_REGION} --instance-ids '${EC2_INSTANCE_ID}' --document-name AWS-RunShellScript --parameters '${ssmJson}' --output text --query 'Command.CommandId'", returnStdout: true).trim()
  if (!commandId) {
    error('SSM send-command did not return a valid command ID.')
  }

  sh "aws ssm wait command-executed --region ${AWS_REGION} --instance-id '${EC2_INSTANCE_ID}' --command-id '${commandId}'"
  def finalStatus = sh(script: "aws ssm get-command-invocation --region ${AWS_REGION} --instance-id '${EC2_INSTANCE_ID}' --command-id '${commandId}' --query 'Status' --output text", returnStdout: true).trim()
  if (finalStatus != 'Success') {
    error("EC2 deployment command failed with status: ${finalStatus}")
  }
}
