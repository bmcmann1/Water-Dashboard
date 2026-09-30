#!/usr/bin/env python3
import os,json,pathlib,smtplib,ssl,email.message
qc=json.loads(pathlib.Path('output/qc_report.json').read_text())
data=json.loads(pathlib.Path('output/normalized_network.json').read_text())
url=os.environ['DASHBOARD_URL'];cov=data.get('coverage',[])
statuses={}
for x in cov: statuses[x.get('status','unknown')]=statuses.get(x.get('status','unknown'),0)+1
checks=data.get('plausibility_checks',[])
issues=[x for x in checks if x.get('status') not in ('PASS','INDETERMINATE','INDETERMINATE_DATUM')]
required=['SMTP_HOST','SMTP_PORT','SMTP_USERNAME','SMTP_PASSWORD','NOTIFY_EMAIL_FROM','NOTIFY_EMAIL_TO']
missing=[k for k in required if not os.environ.get(k)]
if missing: raise SystemExit('Email credentials missing: '+', '.join(missing))
msg=email.message.EmailMessage();msg['From']=os.environ['NOTIFY_EMAIL_FROM'];msg['To']=os.environ['NOTIFY_EMAIL_TO']
msg['Subject']='Mississippi River dashboard updated — '+data['generated_utc'][:10]
msg.set_content('Dashboard: '+url+'\nSnapshot (UTC): '+data['generated_utc']+'\nNetwork nodes: '+str(len(data['nodes']))+'\nCoverage rows by status: '+json.dumps(statuses,sort_keys=True)+'\nPlausibility review flags: '+str(len(issues))+'\nQC report: '+url+'qc_report.json\n\nReview examples:\n'+'\n'.join(str(x)[:300] for x in issues[:15]))
port=int(os.environ['SMTP_PORT']);host=os.environ['SMTP_HOST'];user=os.environ['SMTP_USERNAME'];pw=os.environ['SMTP_PASSWORD']
if port==465:
 with smtplib.SMTP_SSL(host,port,context=ssl.create_default_context(),timeout=30) as s:s.login(user,pw);s.send_message(msg)
else:
 with smtplib.SMTP(host,port,timeout=30) as s:s.starttls(context=ssl.create_default_context());s.login(user,pw);s.send_message(msg)
print('QC email sent')
