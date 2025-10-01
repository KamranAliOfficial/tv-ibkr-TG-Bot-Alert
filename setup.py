"""
Setup script for TradingView-IBKR Trading Bot
"""

import os
import sys
import shutil
from pathlib import Path


def create_directories():
    """Create necessary directories"""
    directories = ['logs', 'configs']
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✓ Created directory: {directory}")


def copy_config_templates():
    """Copy configuration templates if they don't exist"""
    templates = [
        ('config.yaml', 'config.yaml'),
        ('.env.template', '.env')
    ]
    
    for template, target in templates:
        if Path(template).exists() and not Path(target).exists():
            shutil.copy2(template, target)
            print(f"✓ Created {target} from {template}")
        elif not Path(template).exists():
            print(f"⚠ Template {template} not found")
        else:
            print(f"- {target} already exists, skipping")


def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        'flask', 'ib_insync', 'python-telegram-bot', 
        'requests', 'schedule', 'pandas', 'numpy', 
        'pytz', 'pyyaml', 'python-dotenv'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"⚠ Missing packages: {', '.join(missing_packages)}")
        print("Run: pip install -r requirements.txt")
        return False
    else:
        print("✓ All required packages are installed")
        return True


def validate_config():
    """Validate configuration file"""
    config_path = Path('config.yaml')
    
    if not config_path.exists():
        print("⚠ config.yaml not found. Please create it from the template.")
        return False
    
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check required sections
        required_sections = ['bot', 'ibkr', 'webhook', 'trading']
        missing_sections = [section for section in required_sections if section not in config]
        
        if missing_sections:
            print(f"⚠ Missing config sections: {', '.join(missing_sections)}")
            return False
        
        print("✓ Configuration file is valid")
        return True
        
    except Exception as e:
        print(f"⚠ Error validating config: {e}")
        return False


def check_env_file():
    """Check environment file"""
    env_path = Path('.env')
    
    if not env_path.exists():
        print("⚠ .env file not found. Please create it from .env.template")
        return False
    
    # Check for placeholder values
    with open(env_path, 'r') as f:
        content = f.read()
    
    placeholders = ['your_telegram_bot_token', 'your_chat_id', 'your_webhook_secret_key']
    found_placeholders = [p for p in placeholders if p in content]
    
    if found_placeholders:
        print(f"⚠ Please update placeholder values in .env: {', '.join(found_placeholders)}")
        return False
    
    print("✓ Environment file looks good")
    return True


def main():
    """Main setup function"""
    print("TradingView-IBKR Trading Bot Setup")
    print("=" * 40)
    
    # Create directories
    print("\n1. Creating directories...")
    create_directories()
    
    # Copy templates
    print("\n2. Setting up configuration files...")
    copy_config_templates()
    
    # Check dependencies
    print("\n3. Checking dependencies...")
    deps_ok = check_dependencies()
    
    # Validate configuration
    print("\n4. Validating configuration...")
    config_ok = validate_config()
    
    # Check environment file
    print("\n5. Checking environment file...")
    env_ok = check_env_file()
    
    # Summary
    print("\n" + "=" * 40)
    print("Setup Summary:")
    
    if deps_ok and config_ok and env_ok:
        print("✓ Setup completed successfully!")
        print("\nNext steps:")
        print("1. Configure your IBKR connection in config.yaml")
        print("2. Set up your Telegram bot credentials in .env")
        print("3. Start IBKR TWS or IB Gateway")
        print("4. Run: python main.py")
    else:
        print("⚠ Setup completed with warnings. Please address the issues above.")
        
        if not deps_ok:
            print("\n→ Install dependencies: pip install -r requirements.txt")
        if not config_ok:
            print("→ Fix configuration issues in config.yaml")
        if not env_ok:
            print("→ Update placeholder values in .env file")
    
    print("\nFor detailed instructions, see README.md")


if __name__ == "__main__":
    main()