include .env 

.EXPORT_ALL_VARIABLES:
APP_NAME=websocket-chat

# AWS + ECS Credentials
TAG=latest
TF_VAR_app_name=${APP_NAME}
REGISTRY_NAME=${APP_NAME}
TF_VAR_image=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REGISTRY_NAME}:${TAG}
TF_VAR_region=${AWS_REGION}

# Firebase credentials
TF_VAR_firebase_api_key=${FIREBASE_API_KEY}
TF_VAR_firebase_auth_domain=${FIREBASE_AUTH_DOMAIN}
TF_VAR_firebase_database_url=${FIREBASE_DATABASE_URL}
TF_VAR_firebase_project_id=${FIREBASE_PROJECT_ID}
TF_VAR_firebase_storage_bucket=${FIREBASE_STORAGE_BUCKET}
TF_VAR_firebase_messaging_sender_id=${FIREBASE_MESSAGING_SENDER_ID}
TF_VAR_firebase_app_id=${FIREBASE_APP_ID}
TF_VAR_firebase_measurement_id=${FIREBASE_MEASUREMENT_ID}


setup-ecr: 
	cd infra/setup && terraform init && terraform apply -auto-approve

deploy-container:
	cd app && sh deploy.sh

deploy-service:
	cd infra/app && terraform init && terraform apply -auto-approve

destroy-service:
	cd infra/app && terraform init && terraform destroy -auto-approve