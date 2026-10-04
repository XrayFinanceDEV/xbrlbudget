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
        PORT = '9090'
        // Public (non-secret) allowed parent-iframe origins, comma-separated.
        // Must be in environment{} so it is exported to the shell for
        // `docker compose build` — compose resolves ${PARENT_ORIGIN} from the
        // shell env / .env, NOT from .env.docker (that is only the backend env_file).
        PARENT_ORIGIN = 'https://app.formulafinance.it,https://app.kpsfinanciallab.it'
        SUPABASE_JWT_SECRET = credentials('budget-supabase-jwt-secret')
        ANTHROPIC_API_KEY = credentials('budget-anthropic-api-key')
        ADMIN_API_KEY = credentials('budget-admin-api-key')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Generate env') {
            steps {
                script {
                    def base = """\
SUPABASE_JWT_SECRET=${SUPABASE_JWT_SECRET}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ADMIN_API_KEY=${ADMIN_API_KEY}
PARENT_ORIGIN=${PARENT_ORIGIN}
ALLOWED_ORIGINS=https://app.formulafinance.it,https://app.kpsfinanciallab.it
MAX_COMPANIES_PER_USER=50
PORT=9090
""".stripIndent()
                    // Import PDF snello (IMPORT_MOTORE=snello + Qwen su gx10). Questo Jenkinsfile
                    // lo usano staging E produzione: si accende SOLO dove il Jenkins dichiara
                    // la variabile globale IMPORT_MOTORE=snello (Manage Jenkins > System >
                    // Global properties), insieme a GX10_BASE_URL e alla credenziale
                    // secret-text 'budget-gx10-api-key'. Senza, .env.docker resta quello di
                    // sempre e l'import gira sull'importatore attuale.
                    if (env.IMPORT_MOTORE == 'snello') {
                        if (!env.GX10_BASE_URL?.trim()) {
                            error('IMPORT_MOTORE=snello richiede la variabile globale GX10_BASE_URL')
                        }
                        withCredentials([string(credentialsId: 'budget-gx10-api-key', variable: 'GX10_API_KEY')]) {
                            // GX10_CONCORRENZA: il semaforo e' per processo e uvicorn gira con
                            // --workers 2 (backend/entrypoint.sh): 2 x 3 = 6, il massimo che
                            // gx10 deve ricevere in contemporanea.
                            writeFile file: '.env.docker', text: base + """\
IMPORT_MOTORE=snello
PDF_LLM_PROVIDER_COGE=gx10
PDF_LLM_PROVIDER_IVCEE=gx10
PDF_LLM_PROVIDER_DETTAGLI=gx10
GX10_BASE_URL=${env.GX10_BASE_URL.trim()}
GX10_API_KEY=${env.GX10_API_KEY}
GX10_CONCORRENZA=${env.GX10_CONCORRENZA ?: '3'}
""".stripIndent()
                        }
                    } else {
                        writeFile file: '.env.docker', text: base
                    }
                }
            }
        }

        stage('Build') {
            steps {
                sh 'docker compose build --no-cache --parallel'
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
                retry(10) {
                    sleep(time: 5, unit: 'SECONDS')
                    sh 'docker inspect --format="{{.State.Health.Status}}" budget-backend-1 | grep -q healthy'
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
