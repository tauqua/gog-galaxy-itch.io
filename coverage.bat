set my_error=0

py  -3.7-32 -m pip install -r requirements/dev.txt
::py  -3.7-32 -m cProfile -s cumulative -m pytest UnittestProject.py --cov --junit-xml pytest.xml
IF %ERRORLEVEL% NEQ 0 ( 
   set my_error=%ERRORLEVEL%
)
::py  -3.7-32 -m coverage html --omit=galaxy/*


EXIT /B %my_error% 