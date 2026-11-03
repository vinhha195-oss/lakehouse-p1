# Source before running locally on Windows (Git Bash): portable JDK 11 + winutils.
export JAVA_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -W)/_ext/jdk/jdk-11.0.32.1+1"
export HADOOP_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -W)/_ext/hadoop"
export PATH="$(cygpath "$JAVA_HOME")/bin:$(cygpath "$HADOOP_HOME")/bin:$PATH"
export PYSPARK_PYTHON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -W)/.venv/Scripts/python.exe"
export PYTHONUTF8=1
