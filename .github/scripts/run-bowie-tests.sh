#!/bin/bash

# #######################################################################
# Slurm script to run jobs on Bowie Supercomputer Cluster               #
# Info on Bowie: https://open-atmos-krk.github.io/projects/hpc-diy.html #
# Expected arguments:                                                   # 
#   1: Python version (passed to pyenv)                                 #
#   2: command to execute (passed to mpiexec)                           #
# #######################################################################

#SBATCH --output=/mnt/cluster-workspace/gha-runner/pysdm-derlk/logs/stdout.txt
#SBATCH --error=/mnt/cluster-workspace/gha-runner/pysdm-derlk/logs/joberr.txt
#SBATCH --gres=gpu:1

source $HOME/.setup-pyenv
pyenv shell $1
python --version
python -m venv ./.venv
source ./.venv/bin/activate
export PATH=/mnt/cluster-workspace/bin/openmpi-5.0.10/bin:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/mnt/cluster-workspace/bin/openmpi-5.0.10/lib
unset CI

python -c 'import os; print("CI during install:", os.environ.get("CI"))'
env -u CI python -m pip install -e '.[unit-tests]'
curl -fL \
  -H "Authorization: Bearer $3" \
  -H "Accept: application/vnd.github+json" \
  -o artifact.zip \
  "https://api.github.com/repos/Delcior/ThrustRTC/actions/artifacts/8234929096/zip"
unzip artifact.zip
pip install ThrustRTC-0.3.20-py3-none-linux_aarch64.whl

ls -la ./.venv/lib/python3.13/site-packages/ThrustRTC
file ./.venv/lib/python3.13/site-packages/ThrustRTC/libPyThrustRTC.so

$2
exit_code=$?
echo "Tests completed with exit code $exit_code"
echo $exit_code > /mnt/cluster-workspace/gha-runner/runners/pysdm-derlk/test_exit_code.txt