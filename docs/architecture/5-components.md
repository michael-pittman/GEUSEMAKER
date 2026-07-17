# 5. Components

## 5.1 CLI Layer

**Purpose:** User-facing command interface providing rewarding, interactive experience with rich visual feedback

### 5.1.1 ASCII Art & Branding (`geusemaker/cli/branding.py`)

The module exposes `MAIN_BANNER` (the figlet trademark mark), `DEPLOY_BANNER`
(brutalist block art shown at deploy start), the one-line `COMPACT_BANNER`, the
`STAGE_GLYPHS` per-stage marks, and the `EMOJI` dict.

```python
MAIN_BANNER = r"""
   ____                     __  __       _
  / ___| ___ _   _ ___  ___|  \/  | __ _| | _____ _ __
 | |  _ / _ \ | | / __|/ _ \ |\/| |/ _` | |/ / _ \ '__|
 | |_| |  __/ |_| \__ \  __/ |  | | (_| |   <  __/ |
  \____|\___|\__,_|___/\___|_|  |_|\__,_|_|\_\___|_|
"""

# One-line string used for non-TTY / machine-adjacent contexts and the TUI sidebar.
COMPACT_BANNER = "GeuseMaker — AI infrastructure on AWS"

# DEPLOY_BANNER: brutalist GEUSE/MAKER block art (signal lime + ink).
# STAGE_GLYPHS: {"validate": ..., "vpc": ..., "efs": ..., "ec2": ..., ...}
#   compact <=5-line ASCII marks printed when each deployment stage starts.
```
