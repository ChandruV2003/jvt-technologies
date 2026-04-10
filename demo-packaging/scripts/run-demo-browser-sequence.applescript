property siteUrl : "file:///Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site/index.html"
property demoUrl : "http://127.0.0.1:8000/demo"

tell application "Safari"
	activate
	if (count of windows) = 0 then
		make new document
	end if
	set bounds of front window to {90, 80, 1510, 980}
	set current tab of front window to (make new tab at end of tabs of front window with properties {URL:siteUrl})
end tell

delay 6

tell application "Safari"
	set current tab of front window to (make new tab at end of tabs of front window with properties {URL:demoUrl})
end tell

delay 4

tell application "Safari"
	do JavaScript "window.scrollTo(0, 0);" in current tab of front window
	do JavaScript "document.querySelector('#reset-demo-btn').click();" in current tab of front window
end tell

delay 2

tell application "Safari"
	do JavaScript "document.querySelector('#load-sample-pack-btn').click();" in current tab of front window
end tell

delay 4

tell application "Safari"
	do JavaScript "document.querySelector('#provider-select').value = 'mlx-local';" in current tab of front window
	do JavaScript "document.querySelector('[data-question=\"What does the billing policy say about disputed invoices?\"]').click();" in current tab of front window
end tell

delay 1

tell application "Safari"
	do JavaScript "document.querySelector('#question-form button[type=\"submit\"]').click();" in current tab of front window
end tell

delay 7

tell application "Safari"
	do JavaScript "document.querySelector('#citation-list').scrollIntoView({behavior: 'smooth', block: 'center'});" in current tab of front window
end tell

delay 4

tell application "Safari"
	do JavaScript "document.querySelector('[data-question=\"What confidentiality obligations survive termination?\"]').click();" in current tab of front window
end tell

delay 1

tell application "Safari"
	do JavaScript "document.querySelector('#question-form button[type=\"submit\"]').click();" in current tab of front window
end tell

delay 6

tell application "Safari"
	set current tab of front window to tab 1 of front window
	set URL of current tab of front window to siteUrl & "#contact"
end tell

delay 6
