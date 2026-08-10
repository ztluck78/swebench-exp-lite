#!/usr/bin/env bash
# start.sh — swebench-exp-lite 幂等安装（可重复执行，已就绪的步骤自动跳过）
#
# 五步：环境检查 → venv+依赖 → 题库 DB → 评测镜像 → demo 预热，最后安装自检。
# 0.1.0 支持平台：macOS（Docker Desktop）；Ubuntu/Windows/Apple Silicon 慢速优化列入 v1.1+ 路线图。
set -euo pipefail
cd "$(dirname "$0")"

# ---- 0.1.0 资源地址（OSS 镜像 & GitHub Release DB；env 可覆盖） ----
RELEASE_DB_URL="${SWEBENCH_LITE_DB_URL:-https://github.com/ztluck78/swebench-exp-lite/releases/download/0.1.0/swe_bench.db}"
OSS_BASE="${SWEBENCH_LITE_OSS:-https://github-release-data.oss-cn-beijing.aliyuncs.com}"

DEMO_INSTANCE="pylint-dev__pylint-7080"

step() { printf '\n==> [%s] %s\n' "$1" "$2"; }

# ---------- Step 1: 环境检查 ----------
step 1/5 "环境检查（python>=3.10 + docker）"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "错误：找不到 $PY"; exit 1; }
"$PY" - <<'EOF'
import sys
assert sys.version_info >= (3, 10), f"需要 Python>=3.10，当前 {sys.version}"
print(f"python {sys.version.split()[0]} OK")
EOF
command -v docker >/dev/null || { echo "错误：未安装 docker（macOS 请装 Docker Desktop）"; exit 1; }
docker info >/dev/null 2>&1 || { echo "错误：docker daemon 未运行（请启动 Docker Desktop）"; exit 1; }
echo "docker OK"

# ---------- Step 2: venv + 依赖 ----------
step 2/5 "虚拟环境与依赖（幂等）"
if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv
    echo "已创建 .venv"
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .
echo "依赖就绪（docker/tqdm/unidiff/requests 四件套）"

# ---------- Step 3: 题库 DB ----------
step 3/5 "题库 database/swe_bench.db（幂等）"
if [ -f database/swe_bench.db ]; then
    echo "[skip] DB 已存在: database/swe_bench.db"
else
    echo "DB 缺失，尝试下载: $RELEASE_DB_URL"
    if curl -fL --retry 2 -o database/swe_bench.db "$RELEASE_DB_URL"; then
        echo "下载完成"
    else
        rm -f database/swe_bench.db
        echo "错误：DB 下载失败（0.1.0 阶段 Release URL 可能异常或网络受限）。"
        echo "      请手动把 swe_bench.db 放到 database/ 下后重跑本脚本。"
        exit 1
    fi
fi

# ---------- Step 4: 评测镜像 ----------
step 4/5 "评测镜像（inspect 短路 / pull / OSS tar 降级）"
EVAL_IMAGE="$(.venv/bin/python -c "
from swebench_exp_lite.db.query import LiteDB
print(LiteDB().docker_image('$DEMO_INSTANCE'))")"
if docker image inspect "$EVAL_IMAGE" >/dev/null 2>&1; then
    echo "[skip] 镜像本地已存在: $EVAL_IMAGE"
else
    echo "本地缺失，尝试官方拉取: docker pull $EVAL_IMAGE"
    if docker pull "$EVAL_IMAGE"; then
        echo "拉取完成"
    else
        TARBALL="sweb.eval.x86_64.pylint-dev_1776_pylint-7080.tar.gz"
        echo "官方拉取失败，降级 OSS tar: $OSS_BASE/$TARBALL"
        if curl -fL --retry 2 -o "/tmp/$TARBALL" "$OSS_BASE/$TARBALL" \
           && docker load -i "/tmp/$TARBALL"; then
            rm -f "/tmp/$TARBALL"
            echo "OSS tar 加载完成"
        else
            echo "错误：镜像获取失败（0.1.0 阶段 OSS 地址可能异常）。"
            echo "      可手动 docker pull $EVAL_IMAGE 或 docker load 后重跑。"
            exit 1
        fi
    fi
fi

# ---------- Step 5: demo 预热（只跑 S2_prepare） ----------
step 5/5 "demo 预热（S2_prepare：镜像/目录就绪）"
.venv/bin/python - <<EOF
from swebench_exp_lite.pipeline import TaskContext
from swebench_exp_lite.pipeline.stages.s2_prepare import S2Prepare
ctx = TaskContext.from_db("$DEMO_INSTANCE", run_id="warmup", adapter="replay-agent")
ctx.ensure_dirs()
S2Prepare().run(ctx)
print("S2_prepare 预热完成")
EOF

# ---------- 安装自检 ----------
step "自检" "list 冒烟 + DB 323 条断言"
.venv/bin/python -m swebench_exp_lite list --limit 3
.venv/bin/python - <<'EOF'
from swebench_exp_lite.db.query import LiteDB
n = LiteDB().count()
assert n == 323, f"题库应为 323 条，实际 {n}"
print(f"题库断言通过：{n} 条")
EOF

echo
echo "安装完成。下一步：./run_demo.sh（replay-agent 闭环演示，2-5 分钟）"
