#!/bin/bash
# Launch Manga Factory with Local Ollama (GPT-OSS 120B)

echo "🚀 Launching SHINOBI // Manga Factory with Local AI..."
echo "✅ AI Provider: Ollama"
echo "✅ Model: gpt-oss:120b"
echo ""

# Force Ollama mode by unsetting Gemini key
unset GEMINI_API_KEY

# Check if model is ready
if ! ollama list | grep -q "gpt-oss:120b"; then
    echo "⚠️  WARNING: gpt-oss:120b is not fully downloaded yet."
    echo "   The bot will launch, but AI features might fail until download completes."
    echo ""
fi

# Run the app
cd "$(dirname "$0")"
python3 run_app.py
