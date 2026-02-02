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

def sync_single_image(full_image, repo, platform, output_callback=None):
    """同步单个镜像的逻辑
    
    Args:
        full_image: 完整镜像名 (image:tag)
        repo: 目标仓库
        platform: 平台架构 (linux/arm64 或 linux/amd64)
        output_callback: 可选的回调函数，用于接收输出行
    
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
    
    # 执行 Docker 三部曲
    success1, output1 = run_command(f"docker pull --platform {platform} {source_full}", output_callback)
    if not success1:
        return False, messages
    
    success2, output2 = run_command(f"docker tag {source_full} {target_full}", output_callback)
    if not success2:
        return False, messages
    
    success3, output3 = run_command(f"docker push {target_full}", output_callback)
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


def sync_images(images, repo, arch="arm", output_callback=None, docker_auth=None):
    """批量同步镜像的核心函数
    
    Args:
        images: 镜像列表
        repo: 目标仓库
        arch: 架构 ("arm" 或 "amd64")
        output_callback: 可选的回调函数，用于接收输出行
        docker_auth: Docker认证信息，格式: {'registry': 'docker.io', 'username': 'user', 'password': 'pass'}
    
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
    
    # 如果需要认证，先登录
    if docker_auth:
        registry = docker_auth.get('registry', 'docker.io')
        username = docker_auth.get('username')
        password = docker_auth.get('password')
        if username and password:
            if not docker_login(registry, username, password, output_callback):
                log("⚠️ 认证失败，但继续尝试同步（可能使用匿名访问）")
    
    for img in images:
        success, messages = sync_single_image(img, repo, platform, output_callback)
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
    # nargs='+' 表示接受一个或多个参数
    parser.add_argument("images", nargs='+', help="一个或多个原始镜像名 (例如: img1:v1 img2:v2)")
    parser.add_argument("--repo", default="devops-docker-bkrepo.glmszq.com/l10b3a/docker-local", help="目标仓库")
    parser.add_argument("--arch", default="arm", choices=["arm", "amd64"], help="架构")

    args = parser.parse_args()
    
    result = sync_images(args.images, args.repo, args.arch)
    
    if result["fail_list"]:
        sys.exit(1)

if __name__ == "__main__":
    main()