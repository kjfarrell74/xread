#!/bin/bash
# IMMEDIATE SECURITY FIX - Remove API keys from git history

echo "🚨 CRITICAL: Removing exposed API keys from git history"
echo "This will rewrite your git history - ensure you have backups!"

# Step 1: Install git-filter-repo if not available
if ! command -v git-filter-repo &> /dev/null; then
    echo "Installing git-filter-repo..."
    pip install git-filter-repo
fi

# Step 2: Backup current repository
echo "Creating backup..."
cp -r .git .git-backup-$(date +%Y%m%d-%H%M%S)

# Step 3: Rotate API keys IMMEDIATELY
echo "🔄 ROTATE THESE API KEYS NOW:"
echo "1. Perplexity API Key: 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"
echo "2. Gemini API Key: AIzaSyAlEuZdq-guvqu-OyX9PI2ZoxlFOp666A0"
echo ""
echo "Visit your provider dashboards and rotate these keys before continuing!"
read -p "Press ENTER when you have rotated both keys..."

# Step 4: Remove sensitive data from git history
echo "Removing API keys from git history..."

# Create replacements file for git-filter-repo
cat > .api-key-replacements.txt << 'EOF'
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==>REPLACE_WITH_YOUR_PERPLEXITY_API_KEY
AIzaSyAlEuZdq-guvqu-OyX9PI2ZoxlFOp666A0==>REPLACE_WITH_YOUR_GEMINI_API_KEY
EOF

# Remove the exposed keys from all history
git filter-repo --replace-text .api-key-replacements.txt --force

# Step 5: Clean up the config.ini file and move keys to environment
echo "Cleaning config.ini..."
cat > config.ini.template << 'EOF'
[General]
ai_model = perplexity
log_level = INFO

[API Keys]
# DO NOT put real API keys here - use environment variables
perplexity_api_key = REPLACE_WITH_YOUR_PERPLEXITY_API_KEY
gemini_api_key = REPLACE_WITH_YOUR_GEMINI_API_KEY

[Pipeline]
save_failed_html = true
max_images_per_post = 10
report_max_tokens = 2000
report_temperature = 0.1

[Scraper]
nitter_instance = https://nitter.net
fetch_timeout = 30
EOF

# Remove the compromised config.ini
rm config.ini

# Step 6: Update .gitignore to prevent future exposure
echo "Updating .gitignore..."
cat >> .gitignore << 'EOF'

# Sensitive configuration files
config.ini
*.key
*.pem
*.p12
*.pfx
.env.local
.env.production
.env.development
secrets/
EOF

# Step 7: Create proper .env template
echo "Creating .env.example template..."
cat > .env.example << 'EOF'
# XReader Environment Variables Template
# Copy this file to .env and replace with your actual values

# API Keys (required)
PERPLEXITY_API_KEY=pplx-your-key-here
GEMINI_API_KEY=your-gemini-key-here

# Optional Configuration
DATA_DIR=scraped_data
DEBUG_DIR=debug_output
NITTER_INSTANCE=https://nitter.net
SAVE_FAILED_HTML=true
AI_MODEL=perplexity
EOF

# Step 8: Clean up
rm .api-key-replacements.txt

# Step 9: Force garbage collection
echo "Cleaning up repository..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo ""
echo "✅ Security fix complete!"
echo ""
echo "📋 NEXT STEPS (CRITICAL):"
echo "1. Set your new API keys in .env file"
echo "2. Copy .env.example to .env and add real keys"
echo "3. Force push to overwrite remote history:"
echo "   git push origin --force --all"
echo "   git push origin --force --tags"
echo "4. Notify all collaborators to re-clone the repository"
echo "5. Check that the old keys no longer work"
echo ""
echo "⚠️  WARNING: All collaborators must re-clone - old clones contain exposed keys!"

# Step 10: Set proper file permissions
chmod 600 .env.example
if [ -f .env ]; then
    chmod 600 .env
fi

echo "Security fix script completed. Please follow the next steps immediately."
