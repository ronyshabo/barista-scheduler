#!/bin/bash

# Enhanced Barista Scheduler Launcher
# Automatically opens browser and provides better user experience

PROJECT_DIR="/home/rony/Desktop/BaristaScheduler/barista-scheduler"
APP_DIR="$PROJECT_DIR/barista-pay"
VENV_DIR="$PROJECT_DIR/venv"
APP_URL="http://localhost:5000"

# Colors for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Barista Scheduler Launcher${NC}"
echo -e "${BLUE}=================================${NC}"

# Check dependencies
echo -e "${YELLOW}🔍 Checking dependencies...${NC}"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}❌ Virtual environment not found!${NC}"
    echo "Please run setup first."
    read -p "Press Enter to exit..."
    exit 1
fi

if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}❌ App directory not found!${NC}"
    read -p "Press Enter to exit..."
    exit 1
fi

if [ ! -f "$APP_DIR/credentials.json" ]; then
    echo -e "${YELLOW}⚠️  Warning: credentials.json not found${NC}"
    echo "Google Calendar integration may not work."
fi

echo -e "${GREEN}✅ All checks passed!${NC}"
echo ""

# Change to app directory
cd "$APP_DIR" || exit 1

echo -e "${BLUE}📁 Starting from: $APP_DIR${NC}"
echo -e "${BLUE}🔧 Activating virtual environment...${NC}"

# Function to open browser after delay
open_browser() {
    sleep 4
    echo -e "${GREEN}🌐 Opening browser automatically...${NC}"
    
    # Try different browser commands in order of preference
    if command -v xdg-open > /dev/null; then
        xdg-open "$APP_URL" 2>/dev/null && echo -e "${GREEN}✅ Browser opened successfully${NC}"
    elif command -v gnome-open > /dev/null; then
        gnome-open "$APP_URL" 2>/dev/null && echo -e "${GREEN}✅ Browser opened successfully${NC}"
    elif command -v firefox > /dev/null; then
        firefox "$APP_URL" 2>/dev/null & echo -e "${GREEN}✅ Firefox launched${NC}"
    elif command -v google-chrome > /dev/null; then
        google-chrome "$APP_URL" 2>/dev/null & echo -e "${GREEN}✅ Chrome launched${NC}"
    elif command -v chromium-browser > /dev/null; then
        chromium-browser "$APP_URL" 2>/dev/null & echo -e "${GREEN}✅ Chromium launched${NC}"
    else
        echo -e "${YELLOW}⚠️  Auto-browser failed. Please manually visit: $APP_URL${NC}"
    fi
}

# Start browser opener in background
open_browser &

echo -e "${GREEN}🌐 Starting Flask server...${NC}"
echo -e "${GREEN}🌐 Browser will auto-open in 4 seconds...${NC}"
echo -e "${GREEN}✅ App available at: $APP_URL${NC}"
echo -e "${YELLOW}❌ Press Ctrl+C to stop${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""

# Run the app
source "$VENV_DIR/bin/activate" && python3 app.py