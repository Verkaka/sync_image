#!/usr/bin/env python3
"""
Flask Web 应用 - Docker 镜像同步工具
"""
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import sync_image
import image_search
import threading
import queue
import json

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 存储任务状态
tasks = {}
task_counter = 0

def run_sync_task(task_id, images, repo, arch, output_queue, docker_auth=None):
    """在线程中执行同步任务"""
    tasks[task_id] = {
        "status": "running",
        "output": [],
        "success_list": [],
        "fail_list": []
    }
    
    def output_callback(line):
        output_queue.put(line)
        tasks[task_id]["output"].append(line)
    
    try:
        result = sync_image.sync_images(images, repo, arch, output_callback, docker_auth)
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["success_list"] = result["success_list"]
        tasks[task_id]["fail_list"] = result["fail_list"]
        output_queue.put(None)  # 结束标记
    except Exception as e:
        tasks[task_id]["status"] = "error"
        error_msg = f"错误: {str(e)}"
        output_queue.put(error_msg)
        tasks[task_id]["output"].append(error_msg)
        output_queue.put(None)

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/api/sync', methods=['POST'])
def sync():
    """同步镜像 API"""
    global task_counter
    
    try:
        data = request.json
        images = data.get('images', [])
        repo = data.get('repo', 'devops-docker-bkrepo.glmszq.com/l10b3a/docker-local')
        arch = data.get('arch', 'arm')
        docker_auth = data.get('docker_auth', None)  # {'registry': 'docker.io', 'username': 'user', 'password': 'pass'}
        
        if not images:
            return jsonify({"error": "镜像列表不能为空"}), 400
        
        # 验证镜像格式
        for img in images:
            if ':' not in img:
                return jsonify({"error": f"镜像格式错误: {img}，必须为 image:tag 格式"}), 400
        
        # 创建任务
        task_counter += 1
        task_id = f"task_{task_counter}"
        
        # 创建输出队列
        output_queue = queue.Queue()
        
        # 在后台线程中启动同步任务
        thread = threading.Thread(
            target=run_sync_task,
            args=(task_id, images, repo, arch, output_queue, docker_auth)
        )
        thread.daemon = True
        thread.start()
        
        def generate():
            while True:
                try:
                    line = output_queue.get(timeout=1)
                    if line is None:
                        # 发送最终状态
                        final_status = {
                            "type": "status",
                            "task_id": task_id,
                            "status": tasks[task_id]["status"],
                            "success_list": tasks[task_id]["success_list"],
                            "fail_list": tasks[task_id]["fail_list"]
                        }
                        yield f"data: {json.dumps(final_status, ensure_ascii=False)}\n\n"
                        break
                    else:
                        yield f"data: {json.dumps({'type': 'output', 'line': line}, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    # 检查线程是否还在运行
                    if not thread.is_alive() and output_queue.empty():
                        # 线程已结束但队列为空，可能出错
                        if task_id in tasks and tasks[task_id]["status"] != "running":
                            final_status = {
                                "type": "status",
                                "task_id": task_id,
                                "status": tasks[task_id]["status"],
                                "success_list": tasks[task_id]["success_list"],
                                "fail_list": tasks[task_id]["fail_list"]
                            }
                            yield f"data: {json.dumps(final_status, ensure_ascii=False)}\n\n"
                            break
                    continue
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """获取任务状态"""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404
    
    return jsonify(tasks[task_id])

@app.route('/api/tasks', methods=['GET'])
def list_tasks():
    """列出所有任务"""
    return jsonify(tasks)

@app.route('/api/search', methods=['GET'])
def search_image():
    """搜索镜像的tags/版本或镜像名称（Docker Hub模糊搜索）"""
    try:
        image_name = request.args.get('image', '').strip()
        registry = request.args.get('registry', '').strip() or None
        limit = int(request.args.get('limit', 100))
        search_type = request.args.get('type', 'tags')  # 'tags' 或 'images'
        username = request.args.get('username', '').strip() or None
        password = request.args.get('password', '').strip() or None
        
        if not image_name:
            return jsonify({"error": "镜像名称不能为空"}), 400
        
        # 构建认证信息
        auth = None
        if username and password:
            auth = (username, password)
        
        # 如果是Docker Hub且搜索类型为images，进行模糊搜索
        if not registry and search_type == 'images':
            result = image_search.search_docker_hub_images(image_name, limit, auth)
        else:
            # 搜索镜像tags
            result = image_search.search_image_tags(image_name, registry, limit, auth)
        
        return jsonify(result)
    
    except ValueError:
        return jsonify({"error": "limit参数必须是数字"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
