$FUNCTION_APP_NAME = "nebula-telegram-bot"
$RESOURCE_GROUP = "telegram-bot-dev"

func azure functionapp publish $FUNCTION_APP_NAME --resource-group $RESOURCE_GROUP
