pipeline {
    agent any

    triggers {
        githubPush()
    }

    options {
        disableConcurrentBuilds()
        timeout(time: 15, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        COMPOSE_PROJECT_NAME = 'budget'
        COMPOSE_FILE = 'docker-compose.yml'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Verify env') {
            steps {
                script {
                    if (!fileExists('.env.docker')) {
                        error '.env.docker not found. Copy .env.docker.example to .env.docker and fill in secrets on the VPS.'
                    }
                }
            }
        }

        stage('Build') {
            steps {
                sh 'docker compose build --parallel'
            }
        }

        stage('Deploy') {
            steps {
                sh 'docker compose up -d --remove-orphans'
            }
        }

        stage('Health check') {
            steps {
                retry(5) {
                    sleep(time: 5, unit: 'SECONDS')
                    sh 'curl -sf http://127.0.0.1:8080/health'
                }
            }
        }

        stage('Cleanup') {
            steps {
                sh 'docker image prune -f'
            }
        }
    }

    post {
        failure {
            sh '''
                echo "Deploy failed — rolling back to previous images"
                docker compose up -d --remove-orphans
            '''
        }
        always {
            cleanWs(cleanWhenNotBuilt: false)
        }
    }
}
