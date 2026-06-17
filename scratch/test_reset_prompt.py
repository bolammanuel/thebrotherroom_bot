import asyncio
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

async def run_test():
    # Mock Update and Context
    update = MagicMock()
    update.effective_user.id = 5717945202  # Admin ID
    update.effective_chat.type = "private"
    
    query = AsyncMock()
    query.from_user.id = 5717945202
    query.data = "admin_reset_prompt"
    
    # Mock message
    message = AsyncMock()
    message.chat_id = 5717945202
    message.text = "Admin Menu"
    
    query.message = message
    update.callback_query = query
    
    context = MagicMock()
    context.user_data = {}
    
    print("Running simulated button_handler for admin_reset_prompt...")
    try:
        await bot.button_handler(update, context)
        print("Finished without exceptions!")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
