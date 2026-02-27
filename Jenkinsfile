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
        SUPABASE_JWT_SECRET = credentials('budget-supabase-jwt-secret')
        ANTHROPIC_API_KEY = credentials('budget-anthropic-api-key')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Generate env') {
            steps {
                writeFile file: '.env.docker', text: """\
SUPABASE_JWT_SECRET=${SUPABASE_JWT_SECRET}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
PARENT_ORIGIN=https://app.formulafinance.it
ALLOWED_ORIGINS=https://app.formulafinance.it
MAX_COMPANIES_PER_USER=50
PORT=9090
""".stripIndent()
            }
        }

        stage('Build') {
            steps {
                sh 'docker compose build --parallel'
            }
        }

        stage('Deploy') {
            steps {
                sh 'docker compose down --timeout 10'
                sh 'docker compose up -d --remove-orphans'
            }
        }

        stage('Health check') {
            steps {
                retry(5) {
                    sleep(time: 5, unit: 'SECONDS')
                    sh 'curl -sf http://127.0.0.1:9090/health'
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
                echo "Deploy failed — attempting rollback"
                docker compose up -d --remove-orphans || true
            '''
        }
        cleanup {
            cleanWs(cleanWhenNotBuilt: false)
        }
    }
}
