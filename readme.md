# 🎮 Giveaway Tracker - Vercel

Агрегатор бесплатных игр для Vercel.

## 📁 Структура

```
giveaway_code/
├── api/
│   └── index.py      # Vercel serverless function
├── vercel.json       # Vercel config
├── requirements.txt  # Зависимости
└── readme.md         # Этот файл
```

## 🚀 Деплой на Vercel через GitHub

### Шаг 1: Подготовь файлы
Убедись что все файлы в папке проекта:
- `api/index.py`
- `vercel.json`
- `requirements.txt`
- `readme.md`

### Шаг 2: Загрузи на GitHub

```bash
# В папке проекта
git init
git add .
git commit -m "Initial commit - Giveaway Tracker for Vercel"
git branch -M main
git remote add origin https://github.com/ТВОЙ_НИК/giveaway-tracker.git
git push -u origin main
```

### Шаг 3: Подключи к Vercel

1. Открой https://vercel.com
2. Нажми **"Add New Project"**
3. Выбери **"Import Git Repository"**
4. Выбери свой репозиторий `giveaway-tracker`
5. Нажми **"Import"**

### Шаг 4: Настройки деплоя

**Framework Preset:** `Other`  
**Root Directory:** `./` (оставь по умолчанию)  
**Build Command:** оставь пустым  
**Output Directory:** оставь пустым  
**Install Command:** `pip install -r requirements.txt`

### Шаг 5: Deploy

Нажми **"Deploy"** и жди ~2-3 минуты.

Готово! Твой сайт будет доступен по адресу:
`https://giveaway-tracker-ТВОЙ_НИК.vercel.app`

## 📊 API Endpoints

| Endpoint | Описание |
|----------|----------|
| `/` | Веб-интерфейс |
| `/api/giveaways` | JSON со всеми играми |
| `/api/giveaways?refresh=1` | Обновить и вернуть JSON |
| `/api/giveaways?platform=Epic` | Фильтр по платформе |
| `/api/stats` | Статистика |

## ⚠️ Важно для Vercel

- **Serverless функции** имеют лимит 10 секунд на выполнение
- **Кэширование** API ответов на 1 час
- **Автоматический редирект** на HTTPS
- **Бесплатный тариф**: 100GB bandwidth/month

## 🔧 Локальный запуск

```bash
pip install -r requirements.txt
vercel dev
```

Или через uvicorn:
```bash
uvicorn api.index:app --reload
```

## 🎨 Функции

- ✅ 5 платформ (Epic, Steam, GOG, Humble, itch.io)
- ✅ Real-time таймер (обновляется каждую секунду)
- ✅ Фильтры по платформам
- ✅ Табы (All, Games, DLCs, Expired)
- ✅ Неоновый дизайн
- ✅ Адаптивный для мобильных

## 📝 Лицензия

MIT
