## See Dr. Scratch

I am no longer maintaining this project. The source will remain available, however, the heroku instance will not.

For a more up-to-date project please see:

http://drscratch.org/

---

Hairball Demo is a simple web service that demonstrates Hairball, the
lint-inspired static analysis tool for Scratch. The paper and presentation
slides for Hairball can be found at: http://cs.ucsb.edu/~bboe/p/cv#sigcse13

A running version of the Hairball Demo web service can be found at:
http://hairball.herokuapp.com

The Hairball source is located at:
https://github.com/ucsb-cs-education/hairball


## Local Installation

0. Create python virtual environment

    mkvirtualenv hbdemo

0. Install requirements

    pip install -r requirements.txt

0. Run the development server

    gunicorn --worker-class=gevent --timeout 300 --bind 0.0.0.0:<PORT> app:app
