#!/usr/bin/env python3
"""
Docker 镜像搜索模块 - 查询镜像的可用tags/版本
"""
import requests


def parse_image_name(image_name):
    """解析镜像名称，提取registry、namespace和image名称
    
    Args:
        image_name: 镜像名称，如 'nginx', 'library/nginx', 'docker.io/library/nginx'
    
    Returns:
        tuple: (registry, namespace, image)
    """
    # 移除tag部分（如果有）
    if ':' in image_name:
        image_name = image_name.split(':')[0]
    
    # 默认registry
    registry = 'docker.io'
    namespace = 'library'
    image = image_name
    
    # 检查是否包含registry
    if '/' in image_name:
        parts = image_name.split('/')
        # 如果包含点或端口，说明是registry
        if '.' in parts[0] or ':' in parts[0]:
            registry = parts[0]
            if len(parts) >= 3:
                namespace = parts[1]
                image = '/'.join(parts[2:])
            elif len(parts) == 2:
                namespace = 'library'
                image = parts[1]
        else:
            # 没有registry，只有namespace/image
            if len(parts) == 2:
                namespace = parts[0]
                image = parts[1]
            else:
                namespace = 'library'
                image = parts[0]
    
    return registry, namespace, image


def search_docker_hub_tags(image_name, limit=100, auth=None):
    """从Docker Hub搜索镜像的tags
    
    Args:
        image_name: 镜像名称，如 'nginx', 'library/nginx'
        limit: 返回的最大tags数量
        auth: 认证信息 (username, password) 或 None
    
    Returns:
        dict: {'success': bool, 'tags': list, 'error': str}
    """
    try:
        registry, namespace, image = parse_image_name(image_name)
        
        # Docker Hub API
        if registry == 'docker.io' or registry == 'registry-1.docker.io':
            # Docker Hub API v2
            url = f"https://hub.docker.com/v2/repositories/{namespace}/{image}/tags"
            params = {
                'page_size': limit,
                'ordering': '-last_updated'
            }
            
            headers = {}
            if auth:
                from requests.auth import HTTPBasicAuth
                auth_obj = HTTPBasicAuth(auth[0], auth[1])
            else:
                auth_obj = None
            
            tags = []
            page = 1
            
            while len(tags) < limit:
                params['page'] = page
                response = requests.get(url, params=params, auth=auth_obj, headers=headers, timeout=10)
                
                if response.status_code == 404:
                    return {
                        'success': False,
                        'tags': [],
                        'error': f'镜像 {image_name} 不存在于 Docker Hub'
                    }
                
                if response.status_code != 200:
                    return {
                        'success': False,
                        'tags': [],
                        'error': f'Docker Hub API 错误: HTTP {response.status_code}'
                    }
                
                data = response.json()
                results = data.get('results', [])
                
                if not results:
                    break
                
                for result in results:
                    tag_name = result.get('name', '')
                    if tag_name:
                        tags.append({
                            'name': tag_name,
                            'last_updated': result.get('last_updated', ''),
                            'size': result.get('full_size', 0)
                        })
                
                # 检查是否还有更多页面
                if not data.get('next'):
                    break
                
                page += 1
                if page > 10:  # 限制最多10页
                    break
            
            return {
                'success': True,
                'tags': tags[:limit],
                'registry': 'docker.io',
                'namespace': namespace,
                'image': image
            }
        else:
            # 私有仓库，使用Registry API
            return search_registry_tags(registry, namespace, image)
    
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'tags': [],
            'error': f'网络错误: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'tags': [],
            'error': f'搜索错误: {str(e)}'
        }


def search_registry_tags(registry, namespace, image, auth=None):
    """从Docker Registry搜索镜像的tags（支持私有仓库）
    
    Args:
        registry: registry地址，如 'registry.example.com' 或 'https://registry.example.com'
        namespace: 命名空间
        image: 镜像名称
        auth: 认证信息 (username, password) 或 None
    
    Returns:
        dict: {'success': bool, 'tags': list, 'error': str}
    """
    try:
        # 构建镜像路径
        if namespace and namespace != 'library':
            image_path = f"{namespace}/{image}"
        else:
            image_path = image
        
        # 处理registry URL协议
        if registry.startswith('http://') or registry.startswith('https://'):
            base_url = registry
        else:
            # 默认尝试https，如果失败再尝试http
            base_url = f"https://{registry}"
        
        # Registry API v2
        url = f"{base_url}/v2/{image_path}/tags/list"
        
        headers = {}
        if auth:
            from requests.auth import HTTPBasicAuth
            auth_obj = HTTPBasicAuth(auth[0], auth[1])
        else:
            auth_obj = None
        
        response = requests.get(url, auth=auth_obj, headers=headers, timeout=10, verify=False)
        
        # 如果https失败且是默认的https，尝试http
        if response.status_code not in [200, 401, 404] and not registry.startswith('http'):
            base_url = f"http://{registry}"
            url = f"{base_url}/v2/{image_path}/tags/list"
            response = requests.get(url, auth=auth_obj, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 404:
            return {
                'success': False,
                'tags': [],
                'error': f'镜像 {image_path} 不存在于仓库 {registry}'
            }
        
        if response.status_code == 401:
            return {
                'success': False,
                'tags': [],
                'error': f'需要认证才能访问仓库 {registry}'
            }
        
        if response.status_code != 200:
            return {
                'success': False,
                'tags': [],
                'error': f'Registry API 错误: HTTP {response.status_code}'
            }
        
        data = response.json()
        tags_list = data.get('tags', [])
        
        tags = [{'name': tag, 'last_updated': '', 'size': 0} for tag in tags_list]
        
        return {
            'success': True,
            'tags': tags,
            'registry': registry,
            'namespace': namespace,
            'image': image
        }
    
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'tags': [],
            'error': f'网络错误: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'tags': [],
            'error': f'搜索错误: {str(e)}'
        }


def search_docker_hub_images(query, limit=25, auth=None):
    """在Docker Hub中模糊搜索镜像名称
    
    Args:
        query: 搜索关键词，如 'nginx', 'redis'
        limit: 返回的最大镜像数量
        auth: 认证信息 (username, password) 或 None
    
    Returns:
        dict: {'success': bool, 'images': list, 'error': str}
    """
    try:
        url = "https://hub.docker.com/v2/search/repositories"
        params = {
            'q': query,
            'page_size': limit,
            'page': 1
        }
        
        headers = {}
        if auth:
            from requests.auth import HTTPBasicAuth
            auth_obj = HTTPBasicAuth(auth[0], auth[1])
        else:
            auth_obj = None
        
        response = requests.get(url, params=params, auth=auth_obj, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {
                'success': False,
                'images': [],
                'error': f'Docker Hub API 错误: HTTP {response.status_code}'
            }
        
        data = response.json()
        results = data.get('results', [])
        
        images = []
        for result in results:
            repo_name = result.get('repo_name', '')
            if repo_name:
                images.append({
                    'name': repo_name,
                    'description': result.get('short_description', ''),
                    'stars': result.get('star_count', 0),
                    'official': result.get('is_official', False)
                })
        
        return {
            'success': True,
            'images': images,
            'total': data.get('count', 0)
        }
    
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'images': [],
            'error': f'网络错误: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'images': [],
            'error': f'搜索错误: {str(e)}'
        }


def search_image_tags(image_name, registry=None, limit=100, auth=None):
    """搜索镜像的所有tags/版本
    
    Args:
        image_name: 镜像名称，如 'nginx', 'library/nginx', 'namespace/image'
        registry: 指定的registry地址（可选），如 'registry.example.com'。如果为None，则使用Docker Hub
        limit: 返回的最大tags数量
        auth: 认证信息 (username, password) 或 None
    
    Returns:
        dict: {'success': bool, 'tags': list, 'error': str, 'registry': str, ...}
    """
    # 如果指定了registry，使用私有仓库搜索
    if registry and registry not in ['docker.io', 'registry-1.docker.io', 'hub.docker.com']:
        # 解析镜像名称
        registry_parsed, namespace, image = parse_image_name(image_name)
        # 使用指定的registry
        return search_registry_tags(registry, namespace, image, auth)
    else:
        # 使用Docker Hub
        return search_docker_hub_tags(image_name, limit, auth)
