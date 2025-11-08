import time
import psutil
from cachelib import FileSystemCache

# Use thread-safe cache for Docker stats
docker_cache = FileSystemCache('docker_cache_dir', threshold=100)

def get_docker_info():
    """Get Docker container information with stats"""
    try:
        import requests_unixsocket
        import requests
        import json

        # Clean up old entries (older than 10 minutes)
        current_time = time.time()
        # Note: cachelib handles expiration automatically, but we can clean up manually if needed

        # Use requests directly with Unix socket
        session = requests_unixsocket.Session()

        # Get containers
        response = session.get('http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/json?all=true')
        response.raise_for_status()
        containers = response.json()

        docker_stats = []
        for container in containers:
            try:
                container_info = {
                    'id': container['Id'][:12],
                    'name': container['Names'][0][1:] if container['Names'] else 'unknown',
                    'status': container['State'],
                    'image': container['Image'],
                    'ports': container.get('Ports', []),
                    'created': container.get('Created', 'unknown')
                }

                # Get stats for running containers
                if container['State'] == 'running':
                    try:
                        stats_response = session.get(f'http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/{container["Id"]}/stats?stream=false&one-shot=true')
                        if stats_response.status_code == 200:
                            stats = stats_response.json()
                            
                            # CPU usage percentage - use stored previous stats for proper delta calculation
                            container_id = container['Id']
                            current_cpu = stats['cpu_stats']['cpu_usage']['total_usage']
                            current_system = stats['cpu_stats']['system_cpu_usage']
                            online_cpus = len(stats['cpu_stats']['cpu_usage']['percpu_usage']) if 'percpu_usage' in stats['cpu_stats']['cpu_usage'] else psutil.cpu_count()
                            
                            cpu_percent = 0.0
                            prev_data = docker_cache.get(container_id)
                            if prev_data:
                                prev_cpu = prev_data.get('cpu_usage', 0)
                                prev_system = prev_data.get('system_cpu', 0)
                                
                                cpu_delta = current_cpu - prev_cpu
                                system_delta = current_system - prev_system
                                
                                if system_delta > 0 and online_cpus > 0:
                                    cpu_percent = (cpu_delta / system_delta) * online_cpus * 100
                                    cpu_percent = max(0, min(100 * online_cpus, cpu_percent))  # Clamp to reasonable range
                            
                            # Store current stats for next calculation
                            docker_cache.set(container_id, {
                                'cpu_usage': current_cpu,
                                'system_cpu': current_system,
                                'timestamp': time.time()
                            }, timeout=600)  # 10 minutes
                            
                            # Memory usage
                            mem_usage = stats['memory_stats']['usage']
                            mem_limit = stats['memory_stats']['limit']
                            mem_percent = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0
                            
                            # Network I/O
                            net_rx = 0
                            net_tx = 0
                            if 'networks' in stats:
                                for net_stats in stats['networks'].values():
                                    net_rx += net_stats.get('rx_bytes', 0)
                                    net_tx += net_stats.get('tx_bytes', 0)
                            
                            # Block I/O
                            blk_read = 0
                            blk_write = 0
                            if 'blkio_stats' in stats and 'io_service_bytes_recursive' in stats['blkio_stats']:
                                for io_stat in stats['blkio_stats']['io_service_bytes_recursive']:
                                    if io_stat['op'] == 'read':
                                        blk_read += io_stat['value']
                                    elif io_stat['op'] == 'write':
                                        blk_write += io_stat['value']
                            
                            # PIDs
                            pids = stats.get('pids_stats', {}).get('current', 0)
                            
                            container_info.update({
                                'cpu_percent': round(cpu_percent, 2),
                                'mem_usage': mem_usage,
                                'mem_limit': mem_limit,
                                'mem_percent': round(mem_percent, 1),
                                'net_rx': net_rx,
                                'net_tx': net_tx,
                                'blk_read': blk_read,
                                'blk_write': blk_write,
                                'pids': pids
                            })
                        else:
                            # Stats not available
                            container_info.update({
                                'cpu_percent': 0.0,
                                'mem_usage': 0,
                                'mem_limit': 0,
                                'mem_percent': 0.0,
                                'net_rx': 0,
                                'net_tx': 0,
                                'blk_read': 0,
                                'blk_write': 0,
                                'pids': 0
                            })
                    except Exception as stats_error:
                        # Stats failed
                        container_info.update({
                            'cpu_percent': 0.0,
                            'mem_usage': 0,
                            'mem_limit': 0,
                            'mem_percent': 0.0,
                            'net_rx': 0,
                            'net_tx': 0,
                            'blk_read': 0,
                            'blk_write': 0,
                            'pids': 0
                        })
                else:
                    # Not running
                    container_info.update({
                        'cpu_percent': 0.0,
                        'mem_usage': 0,
                        'mem_limit': 0,
                        'mem_percent': 0.0,
                        'net_rx': 0,
                        'net_tx': 0,
                        'blk_read': 0,
                        'blk_write': 0,
                        'pids': 0
                    })

                docker_stats.append(container_info)
            except Exception as e:
                docker_stats.append({
                    'id': container['Id'][:12],
                    'name': container['Names'][0][1:] if container['Names'] else 'unknown',
                    'status': container['State'],
                    'image': container['Image'],
                    'error': str(e),
                    'cpu_percent': 0.0,
                    'mem_usage': 0,
                    'mem_limit': 0,
                    'mem_percent': 0.0,
                    'net_rx': 0,
                    'net_tx': 0,
                    'blk_read': 0,
                    'blk_write': 0,
                    'pids': 0
                })

        return docker_stats
    except Exception as e:
        return [{'error': f'Docker not available: {str(e)}'}]