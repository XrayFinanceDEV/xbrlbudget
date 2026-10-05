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
                    writeFile file: '.env.docker', text: base
                    // Variabili proprie di un server (es. lo staging): una credenziale "Secret
                    // file" 'budget-env-staging', righe KEY=VALORE, accodata a .env.docker.
                    // Questo Jenkinsfile lo usano staging E produzione: il Jenkins che non ha la
                    // credenziale usa il .env.docker di sempre. Il percorso snello (IMPORT_MOTORE=
                    // snello, PDF_LLM_PROVIDER_*=gx10, GX10_BASE_URL, GX10_API_KEY,
                    // GX10_CONCORRENZA) si accende da li': docs/deployment/PRODUCTION_CONFIG.md.
                    try {
                        withCredentials([file(credentialsId: 'budget-env-staging', variable: 'BUDGET_ENV_EXTRA')]) {
                            // tr: un file salvato da Windows porta \r, che finirebbe nei valori.
                            sh 'tr -d "\\r" < "$BUDGET_ENV_EXTRA" >> .env.docker && echo >> .env.docker'
                            sh 'grep -o "^[A-Z_][A-Z0-9_]*=" "$BUDGET_ENV_EXTRA" | tr -d "=" | sed "s/^/budget-env-staging: /"'
                        }
                    } catch (Exception e) {
                        // Solo la credenziale assente vuol dire "niente variabili in piu'";
                        // qualunque altro errore (anche un abort) ferma la build come prima.
                        if (!(e.message ?: '').contains('budget-env-staging')) {
                            throw e
                        }
                        echo 'Credenziale budget-env-staging assente: .env.docker di sempre'
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
