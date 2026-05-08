pipeline {
  agent any

  options {
    timestamps()
    ansiColor('xterm')
  }

  environment {
    AWS_REGION = credentials('aws-region')
    EC2_INSTANCE_ID = credentials('ec2-instance-id')
    SSH_USER = 'ubuntu'
    REMOTE_DIR = '/home/ubuntu/projet_industriel_agi'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Resolve EC2 IP') {
      steps {
        withCredentials([
          string(credentialsId: 'aws-access-key-id', variable: 'AWS_ACCESS_KEY_ID'),
          string(credentialsId: 'aws-secret-access-key', variable: 'AWS_SECRET_ACCESS_KEY')
        ]) {
          sh '''
            set -euo pipefail
            PUBLIC_HOST=$(aws ec2 describe-instances \
              --instance-ids "$EC2_INSTANCE_ID" \
              --region "$AWS_REGION" \
              --query 'Reservations[0].Instances[0].PublicIpAddress' \
              --output text)
            test -n "$PUBLIC_HOST" && test "$PUBLIC_HOST" != "None"
            echo "SSH_HOST=$PUBLIC_HOST" > .jenkins_env
          '''
        }
      }
    }

    stage('Monitor Harness') {
      steps {
        withCredentials([file(credentialsId: 'saif-pipeline-pem', variable: 'SSH_KEY_PATH')]) {
          sh '''
            set -euo pipefail
            source .jenkins_env
            chmod +x scripts/monitor_harness_remote.sh
            SSH_HOST="$SSH_HOST" SSH_KEY_PATH="$SSH_KEY_PATH" SSH_USER="$SSH_USER" REMOTE_DIR="$REMOTE_DIR" \
              bash scripts/monitor_harness_remote.sh
          '''
        }
      }
    }
  }

  post {
    success {
      echo 'Harness monitoring pipeline succeeded.'
    }
    failure {
      echo 'Harness monitoring pipeline failed.'
    }
  }
}

