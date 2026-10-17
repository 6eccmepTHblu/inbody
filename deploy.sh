#!/usr/bin/env bash
# С рабочей машины (Git Bash): запушить и обновить сайт на сервере.
set -euo pipefail
git push
ssh -i ~/.ssh/pcs_vps root@2.27.10.45 /srv/inbody/update.sh
