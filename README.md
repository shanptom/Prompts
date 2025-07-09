Prompts used in AI tools for repetitive tasks

```bash
cd /mnt/d/AIAgents/lba/
source lba/bin/activate
sudo systemctl start docker
sudo systemctl enable docker
docker run -t --rm -p 8070:8070 lfoppiano/grobid:0.8.0
curl -X POST -F "input=@pone.pdf" http://localhost:8070/api/processHeaderDocument
python3 article_classifier_pdf.py
```
