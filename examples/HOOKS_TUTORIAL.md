# How to Use Memovich Hooks (Auto-Save)

Memovich hooks act as an "Auto-Save" feature. They help your AI keep a permanent memory without you needing to run manual commands.

### 1. What are these hooks?
* **Save Hook** (`memovich_save_hook.sh`): Saves new facts and decisions every 15 messages.
* **PreCompact Hook** (`memovich_precompact_hook.sh`): Saves your context right before the AI's memory window fills up.

### 2. Setup for Claude Code
Add this to your configuration file to enable automatic background saving:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "", 
        "hooks": [{"type": "command", "command": "./hooks/memovich_save_hook.sh"}]
      }
    ],
    "PreCompact": [
      {
        "matcher": "", 
        "hooks": [{"type": "command", "command": "./hooks/memovich_precompact_hook.sh"}]
      }
    ]
  }
}