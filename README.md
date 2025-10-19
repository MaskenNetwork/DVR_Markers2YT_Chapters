# DaVinci Resolve Markers to YouTube Chapters

![Bot Profile Picture](bot_propic.png)

This Python Telegram Bot helps DaVinci Resolve users convert their `.edl` (Edit Decision List) files containing markers into a formatted list of YouTube chapters. This allows for easy copy-pasting into YouTube video descriptions, saving time and streamlining the chapter creation process.

## Features

*   **EDL File Processing**: Upload your DaVinci Resolve `.edl` file directly to the bot.
*   **Customizable Marker Color**: Choose which marker color from your DaVinci Resolve project should be used to extract chapters.
*   **Customizable Chapter Separator**: Define your preferred separator for the chapter timestamps and titles (e.g., `-`, `|`, `->`).
*   **User Preferences**: The bot remembers your chosen marker color and chapter separator for future use.

## How to Use

1.  **Start the Bot**: Send `/start` to the bot to get a welcome message and instructions.
2.  **Change Marker Color**: Use the `/color` command or click the "🎨 Change Markers Color 🎨" button to select a specific marker color from DaVinci Resolve (e.g., Blue, Green, Red) that the bot should look for.
3.  **Change Chapter Separator**: Use the `/separator` command or click the "↔️ Change Chapters Separator ↔️" button to set your desired separator character.
4.  **Upload EDL File**: Click the 📎 icon in Telegram to attach and send your `.edl` file.
5.  **Receive Chapters**: The bot will process your file and send back a formatted list of chapters, ready to be copied to YouTube.
6.  **Get Help**: Use the `/help` command or click the "⚙️ Help ⚙️" button for a summary of commands and usage.

## Setup and Installation

To run this bot locally, follow these steps:

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/DV_Markers2YT_Chapters.git
cd DVR_Markers2YT_Chapters
```

### 2. Create and Configure Environment Variables

Copy the `.env.template` file to `.env` and fill in your details:

```bash
cp .env.template .env
```

Open the newly created `.env` file and provide the following:

*   `TELEGRAM_BOT_TOKEN`: Obtain this from BotFather creating your own bot on Telegram.

*You can edit all the other variables in the `.env` file as needed.*

### 3. Install Dependencies

It's recommended to use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Run the Bot

```bash
python bot.py
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an Issue.