const https = require('https');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

class TtsApi {
    constructor(config) {
        this.config = config;
        this.api_url = config.api_url;
        this.api_key = config.api_key;
        this.total_timeout = config.total_timeout || 10;
    }
    
    makeRequest(method, endpoint, data, callback) {
        const url = new URL(this.api_url + endpoint);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname + url.search,
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'auth-key': `Bearer ${this.api_key}`
            }
        };
    
        const req = https.request(options, (res) => {
            // 检查内容类型是否为 'audio/wav'
            if (res.headers['content-type'] === 'audio/wav') {
                const chunks = [];
                res.on('data', (chunk) => {
                    chunks.push(chunk);
                });
                res.on('end', () => {
                    // Buffer.concat将所有的二进制数据块拼接在一起
                    const binaryData = Buffer.concat(chunks);
                    callback(null, binaryData, res);
                });
            } else {
                res.setEncoding('utf8');
                let responseBody = '';
                res.on('data', (chunk) => {
                    responseBody += chunk;
                });
                res.on('end', () => {
                    try {
                        const responseJson = JSON.parse(responseBody);
                        callback(null, responseJson, res);
                    } catch (e) {
                        callback(e);
                    }
                });
            }
        });
    
        req.on('error', (err) => {
            callback(err);
        });
    
        if (data) {
            req.write(JSON.stringify(data));
        }
    
        req.end();
    }

    getModelList(callback) {
        this.makeRequest('GET', '/model_list', null, (err, data, res) => {
            if (err) {
                console.error(err);
                return callback(err, null);
            }
            if (res.statusCode === 200) {
                callback(null, data);
            } else if (res.statusCode === 422) {
                callback(new Error('Authorization failed.'), null);
            } else {
                callback(new Error(`Error: ${res.statusCode}`), null);
            }
        });
    }

    convert(model, content, callback) {
        const data = { model, content };
        this.makeRequest('POST', '/task', data, (err, data, res) => {
            if (err) {
                console.error(err);
                return callback(err, null);
            }
            const isSubmitted = res.statusCode === 200 || res.statusCode === 201;
            if (isSubmitted && data && data.status === 'SUBMITTED') {
                return callback(null, {
                    message: `Task submitted with ID: ${data.task_id}`,
                    taskId: data.task_id
                });
            } else if (res.statusCode === 422) {
                return callback(new Error('Authorization key error'), null);
            } else if (res.statusCode === 400) {
                const detail = data.detail || 'No detail provided';
                return callback(new Error(detail), null);
            } else {
                return callback(new Error('Service error'), null);
            }
        });
    }

    pollForResult(taskId, callback) {
        const start_time = Date.now();
        const total_timeout = 60 * 1000 * this.total_timeout;
        const interval = setInterval(() => {
            if ((Date.now() - start_time) > total_timeout) {
                clearInterval(interval);
                return callback(new Error('Request timeout: exceeded waiting time'), null);
            }

            this.makeRequest('GET', `/task/${taskId}`, null, (err, data, res) => {
                if (err) {
                    console.error(err);
                    clearInterval(interval);
                    return callback(err, null);
                }
                
                if (res.headers['content-type'] === 'audio/wav') {
                    clearInterval(interval);
                    const tmpDir = path.join(__dirname, 'tmp');
                    if (!fs.existsSync(tmpDir)){
                        fs.mkdirSync(tmpDir);
                    }
                    const filename = path.join(tmpDir, `${taskId}.wav`);
                    fs.writeFile(filename, data, 'binary', (err) => {
                        if (err) {
                            return callback(err, null);
                        }
                        callback(null, {
                            message: "TTS conversion successful",
                            filename: filename
                        });
                    });
                } else if (data.status !== 'SUCCESS') {
                    console.log(`Task status: ${data.status}`);
                }
            });
        }, 1000);
    }
}

function main() {
    const config = {
        api_url: '',
        api_key: ''
    };

    const ttsApi = new TtsApi(config);
    
    ttsApi.getModelList((err, modelList) => {
        if (err) return console.log('Model list fetch error:', err);
        console.log('Model list:', modelList);
    });

    const model = 'leidianjiangjun';
    const content = '大家好，我是雷电将军';
    
    ttsApi.convert(model, content, (err, result) => {
        if (err) return console.log('Conversion error:', err);
        console.log(result.message);
        ttsApi.pollForResult(result.taskId, (err, result) => {
            if (err) return console.log('Polling error:', err);
            console.log(result.message);
            console.log('Audio file saved:', result.filename);
        });
    });
}

main();