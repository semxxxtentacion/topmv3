#!/bin/bash

USER="root"
SERVER_IP="194.87.86.199"
REMOTE_PATH="/var/www/admin"
LOCAL_BUILD_PATH="dist"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

npm run build

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Ошибка при сборке проекта!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Сборка завершена успешно${NC}\n"

echo -e "${YELLOW}🗑️  Шаг 2: Удаление старых файлов на сервере...${NC}"
ssh ${USER}@${SERVER_IP} "rm -rf ${REMOTE_PATH}/*"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Ошибка при удалении старых файлов!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Старые файлы удалены${NC}\n"

echo -e "${YELLOW}📤 Шаг 3: Загрузка нового билда на сервер...${NC}"
scp -r ${LOCAL_BUILD_PATH}/* ${USER}@${SERVER_IP}:${REMOTE_PATH}/

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Ошибка при загрузке файлов!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Файлы загружены успешно${NC}\n"

echo -e "${GREEN}🎉 Деплой завершен успешно!${NC}"
echo -e "${GREEN}Сайт обновлен: ${SERVER_IP}${REMOTE_PATH}${NC}"

