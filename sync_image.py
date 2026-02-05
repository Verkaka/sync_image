import subprocess
import sys
import argparse

def run_command(command, output_callback=None):
    """执行 Shell 命令并实时打印输出
    
    Args:
        command: 要执行的命令
        output_callback: 可选的回调函数，用于接收输出行 (line) -> None
    
    Returns:
        tuple: (success: bool, output_lines: list)
    """
    output_lines = []
    if output_callback is None:
        print(f"🚀 运行: {command}")
    
    process = subprocess.Popen(
        command, shell=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,
        text=True
    )
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            line = output.strip()
            output_lines.append(line)
            if output_callback:
                output_callback(line)
            else:
                print(f"  > {line}")
    
    success = process.poll() == 0
    return success, output_lines

def image_exists_locally(full_image):
    """检查镜像是否已存在于本地（docker image inspect）。
    
    Returns:
        bool: 存在返回 True，否则 False
    """
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", full_image],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def sync_single_image(full_image, repo, platform, output_callback=None, use_local=False):
    """同步单个镜像的逻辑。
    
    若 use_local=True 且镜像本地已存在，则跳过拉取，仅执行 tag + push。
    
    Args:
        full_image: 完整镜像名 (image:tag)
        repo: 目标仓库
        platform: 平台架构 (linux/arm64 或 linux/amd64)
        output_callback: 可选的回调函数，用于接收输出行
        use_local: 是否优先使用本地已有镜像（存在则跳过 pull）
    
    Returns:
        tuple: (success: bool, messages: list)
    """
    messages = []
    
    def log(msg):
        messages.append(msg)
        if output_callback:
            output_callback(msg)
        else:
            print(msg)
    
    if ":" not in full_image:
        error_msg = f"❌ 跳过: '{full_image}' (格式错误，需为 image:tag)"
        log(error_msg)
        return False, messages
    
    source_full = full_image
    image_part = source_full.split(":")[0]
    tag_part = source_full.split(":")[1]
    short_name = image_part.split('/')[-1]
    target_full = f"{repo}/{short_name}:{tag_part}"
    
    log(f"\n[正在处理] {source_full} -> {target_full}")
    
    # 若启用“使用本地镜像”且本地已存在，则跳过拉取
    skip_pull = False
    if use_local and image_exists_locally(source_full):
        log("📦 使用本地已有镜像，跳过拉取")
        skip_pull = True
    
    if not skip_pull:
        success1, _ = run_command(f"docker pull --platform {platform} {source_full}", output_callback)
        if not success1:
            return False, messages
    
    success2, _ = run_command(f"docker tag {source_full} {target_full}", output_callback)
    if not success2:
        return False, messages
    
    success3, _ = run_command(f"docker push {target_full}", output_callback)
    if not success3:
        return False, messages
    
    return True, messages

def docker_login(registry, username=None, password=None, output_callback=None):
    """执行 Docker 登录
    
    Args:
        registry: registry地址，如 'docker.io', 'registry.example.com'
        username: 用户名（可选）
        password: 密码或token（可选）
        output_callback: 可选的回调函数
    
    Returns:
        bool: 是否成功
    """
    if not username or not password:
        return True  # 无需认证
    
    def log(msg):
        if output_callback:
            output_callback(msg)
        else:
            print(msg)
    
    # 使用 subprocess 直接传递密码到 stdin，避免在命令行中显示
    import subprocess
    import shlex
    
    log(f"🔐 正在登录到 {registry}...")
    
    try:
        # 使用 subprocess.Popen 直接传递密码
        process = subprocess.Popen(
            ['docker', 'login', registry, '-u', username, '--password-stdin'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        stdout, _ = process.communicate(input=password, timeout=30)
        
        if process.returncode == 0:
            log(f"✅ 登录成功")
            if output_callback:
                for line in stdout.strip().split('\n'):
                    if line:
                        output_callback(f"  > {line}")
            return True
        else:
            log(f"❌ 登录失败: {stdout.strip()}")
            if output_callback:
                for line in stdout.strip().split('\n'):
                    if line:
                        output_callback(f"  > {line}")
            return False
    except subprocess.TimeoutExpired:
        log(f"❌ 登录超时")
        return False
    except Exception as e:
        log(f"❌ 登录错误: {str(e)}")
        return False


def get_image_registry(full_image: str) -> str:
    """从镜像名推断 registry。

    规则（与 docker 的默认行为一致的近似）：
    - `nginx:latest` / `library/nginx:latest` -> docker.io
    - `o2cr.ai/openobserve/openobserve-enterprise:latest` -> o2cr.ai
    - `localhost:5000/repo/img:tag` -> localhost:5000
    """
    # 去掉 tag / digest
    name = full_image
    if "@" in name:
        name = name.split("@", 1)[0]
    if ":" in name:
        # 注意：这里的 ":" 也可能属于 host:port，但在有 "/" 的情况下更安全：
        # 先按 "/" 判断第一段是否为 registry（包含 "." 或 ":" 或为 localhost）
        pass

    parts = name.split("/")
    if len(parts) == 1:
        return "docker.io"

    first = parts[0]
    if first == "localhost" or "." in first or ":" in first:
        return first
    return "docker.io"


def sync_images(images, repo, arch="arm", output_callback=None, docker_auth=None, use_local=False):
    """批量同步镜像的核心函数
    
    Args:
        images: 镜像列表
        repo: 目标仓库
        arch: 架构 ("arm" 或 "amd64")
        output_callback: 可选的回调函数，用于接收输出行
        docker_auth: Docker认证信息，格式: {'registry': 'docker.io', 'username': 'user', 'password': 'pass'}
        use_local: 若镜像本地已存在则跳过拉取，直接 tag + push
    
    Returns:
        dict: 包含 success_list, fail_list, messages 的字典
    """
    arch_map = {"arm": "linux/arm64", "amd64": "linux/amd64"}
    platform = arch_map[arch]
    
    success_list = []
    fail_list = []
    all_messages = []
    
    def log(msg):
        all_messages.append(msg)
        if output_callback:
            output_callback(msg)
        else:
            print(msg)
    
    log(f"开始批量同步，目标架构: {platform}\n")
    
    # 如果需要认证：仅在本次待同步镜像里包含对应 registry 时才登录
    if docker_auth:
        auth_registry = (docker_auth.get("registry") or "docker.io").strip()
        username = docker_auth.get("username")
        password = docker_auth.get("password")

        registries_in_images = {get_image_registry(img) for img in images}
        should_login = auth_registry in registries_in_images

        # 兼容：docker.io / index.docker.io / registry-1.docker.io 视为同一类
        dockerhub_aliases = {"docker.io", "index.docker.io", "registry-1.docker.io"}
        if auth_registry in dockerhub_aliases and ("docker.io" in registries_in_images):
            should_login = True

        if should_login and username and password:
            if not docker_login(auth_registry, username, password, output_callback):
                log("⚠️ 认证失败，但继续尝试同步（可能使用匿名访问）")
    
    for img in images:
        success, messages = sync_single_image(img, repo, platform, output_callback, use_local=use_local)
        all_messages.extend(messages)
        if success:
            success_list.append(img)
        else:
            fail_list.append(img)
    
    # 生成最终报告
    report = f"\n{'='*40}\n"
    report += f"📊 同步报告:\n"
    report += f"✅ 成功 ({len(success_list)}): {', '.join(success_list) if success_list else '无'}\n"
    report += f"❌ 失败 ({len(fail_list)}): {', '.join(fail_list) if fail_list else '无'}\n"
    report += f"{'='*40}"
    log(report)
    
    return {
        "success_list": success_list,
        "fail_list": fail_list,
        "messages": all_messages
    }

def main():
    parser = argparse.ArgumentParser(description="批量 Docker 镜像迁移工具")
    parser.add_argument("images", nargs='+', help="一个或多个原始镜像名 (例如: img1:v1 img2:v2)")
    parser.add_argument("--repo", required=True, help="目标仓库地址（必填）")
    parser.add_argument("--arch", default="arm", choices=["arm", "amd64"], help="架构")
    parser.add_argument("--use-local", action="store_true", help="优先使用本地已有镜像，存在则跳过拉取")

    args = parser.parse_args()
    
    result = sync_images(args.images, args.repo, args.arch, use_local=args.use_local)
    
    if result["fail_list"]:
        sys.exit(1)

if __name__ == "__main__":
    main()