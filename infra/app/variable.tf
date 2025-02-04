variable "app_name" {
  description = "Name of the app."
  type        = string
}
variable "region" {
  description = "AWS region to deploy the network to."
  type        = string
}
variable "image" {
  description = "Image used to start the container. Should be in repository-url/image:tag format."
  type        = string
}

# variable "firebase_api_key" {
#   description = "Firebase API key."
#   type        = string
# }
# variable "firebase_auth_domain" {
#   description = "Firebase auth domain."
#   type        = string
# }
# variable "firebase_database_url" {
#   description = "Firebase database URL."
#   type        = string
# }
# variable "firebase_project_id" {
#   description = "Firebase project ID."
#   type        = string
# }
# variable "firebase_storage_bucket" {
#   description = "Firebase storage bucket."
#   type        = string
# }
# variable "firebase_messaging_sender_id" {
#   description = "Firebase messaging sender ID."
#   type        = string
# }
# variable "firebase_app_id" {
#   description = "Firebase app ID."
#   type        = string
# }
# variable "firebase_measurement_id" {
#   description = "Firebase measurement ID."
#   type        = string
# }