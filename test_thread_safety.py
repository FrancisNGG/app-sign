import threading
import time
from modules import safe_print

def task(name, iterations):
    for i in range(iterations):
        safe_print(f"[{name}] 输出 {i}")
        time.sleep(0.01)

# 创建多个线程
threads = []
for i in range(5):
    t = threading.Thread(target=task, args=(f"任务{i+1}", 5))
    threads.append(t)
    t.start()

# 等待所有线程完成
for t in threads:
    t.join()

print("\n测试完成")
