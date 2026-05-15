import json, requests, time, uuid

BASE='http://127.0.0.1:28000/api'
USERNAME='memtest_' + uuid.uuid4().hex[:8]
PASSWORD='Test123456'
EMAIL=f'{USERNAME}@example.com'

KNOWLEDGE_MD = '''# 军事设施保护条例解读

## 主管机关职责
军事设施保护工作由军地有关主管机关按照职责分工协同负责，重点包括保护规划、审批协调与安全监督。

## 审批流程
涉及军事设施保护区的建设活动，应当先履行审查审批程序，再组织施工。审批时需要提交项目说明、位置资料和安全影响评估。

## 法律责任
违反保护要求造成军事设施损害的，依法追究行政责任；构成犯罪的，依法追究刑事责任。
'''

def reg_login():
    requests.post(BASE+'/auth/register', json={'username':USERNAME,'password':PASSWORD,'email':EMAIL,'is_superuser':False}, timeout=30)
    r=requests.post(BASE+'/auth/login', data={'username':USERNAME,'password':PASSWORD}, headers={'Content-Type':'application/x-www-form-urlencoded'}, timeout=30)
    r.raise_for_status()
    return {'Authorization': 'Bearer ' + r.json()['access_token']}


def wait_vectorized(doc_id, headers, timeout=180):
    start=time.time()
    while time.time()-start < timeout:
        r=requests.get(BASE+f'/documents/{doc_id}/vectorize/status', headers=headers, timeout=20)
        data=r.json()
        if data.get('status') == 'completed':
            return data
        if data.get('status') == 'error':
            raise RuntimeError(data)
        time.sleep(2)
    raise TimeoutError('vectorize timeout')


def main():
    headers=reg_login()
    out={}

    r=requests.post(BASE+'/folders', json={'name':'记忆检索测试库','parentId':'root'}, headers=headers, timeout=30)
    folder=r.json(); out['folder']=folder

    files={'file': ('military_rules.txt', KNOWLEDGE_MD.encode('utf-8'), 'text/plain')}
    data={'folderId': folder['id']}
    r=requests.post(BASE+'/documents/upload', files=files, data=data, headers=headers, timeout=60)
    upload=r.json(); out['upload']=upload
    doc_id=upload['documentId']

    # 上传 txt 只是入库，补写 markdownContent 后再向量化
    requests.put(BASE+f'/documents/{doc_id}/content', json={'markdownContent': KNOWLEDGE_MD}, headers=headers, timeout=60).raise_for_status()
    requests.post(BASE+f'/documents/{doc_id}/vectorize', headers=headers, timeout=60).raise_for_status()
    out['vectorize']=wait_vectorized(doc_id, headers)

    # 创建混合对话并测试多轮记忆
    r=requests.post(BASE+'/hybrid/conversations', json={'folderId': folder['id'], 'firstQuestion': '请概括这份材料主要讲了什么？'}, headers=headers, timeout=120)
    conv=r.json(); out['conv_create']=conv
    cid=conv['conversationId']

    # 第二轮：省略主语，测试是否记住“这份材料”与上轮意图
    r=requests.post(BASE+'/hybrid/ask', json={'question':'它提到的审批流程要点是什么？','folderId': folder['id'], 'conversationId': cid}, headers=headers, timeout=120)
    out['turn2']=r.json()

    # 第三轮：继续省略主语，测试是否记住“它”并命中法律责任
    r=requests.post(BASE+'/hybrid/ask', json={'question':'那如果违反要求，会承担什么责任？','folderId': folder['id'], 'conversationId': cid}, headers=headers, timeout=120)
    out['turn3']=r.json()

    # 检索-only
    r=requests.post(BASE+'/hybrid/search', json={'question':'审批流程 安全影响评估','folderId': folder['id']}, headers=headers, timeout=120)
    out['search']=r.json()

    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
