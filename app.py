import flask
import json
import kurt
import os
import time
from hairball import Hairball
from hashlib import sha1
from pprint import pformat
from shutil import copytree, rmtree
from stat import S_ISREG, ST_CTIME, ST_MODE


DATA_DIR = 'data'
KEEP_ALIVE_DELAY = 25
MAX_PROJECTS = 10
MAX_DURATION = 300

app = flask.Flask(__name__, static_folder=DATA_DIR)


if __name__ != '__main__':
    from gevent.event import AsyncResult, Timeout
    from gevent.queue import Empty, Queue
    PRODUCTION = True
    INCLUDES = """<script src="//ajax.googleapis.com/ajax/libs/jquery/1.9.1/jquery.min.js"></script>
<script src="//ajax.googleapis.com/ajax/libs/jqueryui/1.10.1/jquery-ui.min.js"></script>
<link rel="stylesheet" href="//ajax.googleapis.com/ajax/libs/jqueryui/1.10.1/themes/vader/jquery-ui.css" />"""
    broadcast_queue = Queue()
    # Make DATA_DIR if it does not already exist
    try:
        os.mkdir(DATA_DIR)
    except OSError:
        pass
else:
    STATIC_DIR = 'static'
    PRODUCTION = False
    INCLUDES = """<script src="/data/jquery.min.js"></script>
<script src="/data/jquery-ui.min.js"></script>
<link rel="stylesheet" href="/data/jquery-ui.css" />"""
    # Copy static files (and created DATA_DIR) if it doesn't exist
    if not os.path.isdir(DATA_DIR):
        copytree(STATIC_DIR, DATA_DIR)


def broadcast(message):
    """Notify all waiting waiting gthreads of message."""
    waiting = []
    try:
        while True:
            waiting.append(broadcast_queue.get(block=False))
    except Empty:
        pass
    print('Broadcasting {0} messages'.format(len(waiting)))
    for item in waiting:
        item.set(message)


def receive():
    """Generator that yields a message at least every KEEP_ALIVE_DELAY seconds.

    yields messages sent by `broadcast`.

    """
    now = time.time()
    end = now + MAX_DURATION
    tmp = None
    # Heroku doesn't notify when client disconnect so we have to impose a
    # maximum connection duration.
    while now < end:
        if not tmp:
            tmp = AsyncResult()
            broadcast_queue.put(tmp)
        try:
            yield tmp.get(timeout=KEEP_ALIVE_DELAY)
            tmp = None
        except Timeout:
            yield ''
        now = time.time()


def safe_addr(ip_addr):
    """Strip of the trailing two octets of the IP address."""
    return '.'.join(ip_addr.split('.')[:2] + ['xxx', 'xxx'])


def format_broadcast_receive_results(results):
    import pprint
    pprint.pprint(results)
    return 'foobar'


def format_initialization_results(results):
    retval = ''
    for sprite, result in sorted(results['initialized'].items()):
        failed = [x for x in result if result[x] == 1]  # 1 is STATE_MODIFIED

        if failed:
            info = '- FAIL <ul>{0}</ul>'.format(
                ''.join(['<li>{0}</li>'.format(x) for x in sorted(failed)]))
        else:
            info = 'PASS'
        retval += '<div>Sprite: {0} -- {1}</div>\n'.format(sprite, info)
    return retval


def process_scratch(path, data):
    scratch = kurt.ScratchProjectFile(path, load=False)
    scratch._load(data)
    # Setup hairball
    hairball = Hairball(['-p', 'initialization.AttributeInitialization',
                         '-p', 'checks.BroadcastReceive', 'dummy'])
    hairball.initialize_plugins()
    # Create the results directory (if it doesn't already exist)
    try:
        os.mkdir(path)
    except OSError:
        pass
    # Save thumbnail
    scratch.info['thumbnail'].save(os.path.join(path, 'thumbnail.jpg'))

    # Create template
    with open(os.path.join(path, 'index.html'), 'w') as fp:
        fp.write("""<img src="/{path}/thumbnail.jpg" />""".format(path=path))
        # Run the plugins
        for plugin in hairball.plugins:
            name = plugin.__class__.__name__
            results = plugin._process(scratch)
            if name == 'AttributeInitialization':
                name = 'Initialization'
                retval = format_initialization_results(results)
            elif name == 'BroadcastReceive':
                name = 'Broadcast and Receive'
                retval = format_broadcast_receive_results(results)
            else:
                retval = 'Unknown plugin'
            fp.write('<div class="plugin"><h3>Plugin: {name}</h3>\n{contents}</div>'
                     .format(name=name, contents=retval))
    return True


def event_stream(client):
    if not PRODUCTION:
        return
    force_disconnect = False
    try:
        for message in receive():
            yield 'data: {0}\n\n'.format(message)
        print('{0} force closing stream'.format(client))
        force_disconnect = True
    finally:
        if not force_disconnect:
            print('{0} disconnected from stream'.format(client))


@app.route('/post', methods=['POST'])
def post():
    sha1sum = sha1(flask.request.data).hexdigest()
    target = os.path.join(DATA_DIR, '{0}'.format(sha1sum))
    try:
        if process_scratch(target, flask.request.data) and PRODUCTION:
            message = json.dumps({'data': open(os.path.join(target,
                                                            'index.html')).read(),
                                  'ip_addr': safe_addr(flask.request.access_route[0])})
            broadcast(message)  # Notify subscribers of completion
    except Exception as e:  # Output errors
        return '{0}'.format(e)
    return 'success'


@app.route('/stream')
def stream():
    return flask.Response(event_stream(flask.request.access_route[0]),
                          mimetype='text/event-stream')


@app.route('/')
def home():
    # Code adapted from: http://stackoverflow.com/questions/168409/
    infos = []
    for filename in os.listdir(DATA_DIR):
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.isdir(filepath) and filename != 'images':
            file_stat = os.stat(filepath)
            infos.append((file_stat[ST_CTIME], filepath))
    scratch_files = []
    for i, (_, path) in enumerate(sorted(infos, reverse=True)):
        index = os.path.join(path, 'index.html')
        if i >= MAX_PROJECTS or not os.path.isfile(index):
            rmtree(path)
            continue
        scratch_files.append('<div class="analysis">{0}</div>'.format(open(index).read()))
    retval = """
<!doctype html>
<title>Scratch Uploader (Hairball Demo)</title>
<meta charset="utf-8" />
%s

<style>
  body {
    max-width: 800px;
    margin: auto;
    padding: 1em;
    background: black;
    color: #fff;
    font: 16px/1.6 menlo, monospace;
    text-align:center;
  }

  a {
    color: #fff;
  }

  .notice {
    font-size: 80%%;
  }

  .analysis {
    border: 3px solid white;
  }

  .plugin {
    text-align: left;
    border: 1px dashed white;
  }


#drop {
    font-weight: bold;
    text-align: center;
    padding: 1em 0;
    margin: 1em 0;
    color: #555;
    border: 2px dashed #555;
    border-radius: 7px;
    cursor: default;
}

#drop.hover {
    color: #f00;
    border-color: #f00;
    border-style: solid;
    box-shadow: inset 0 3px 4px #888;
}

</style>
<h3>Scratch Uploader (Hairball Demo)</h3>
<noscript>Note: You must have javascript enabled in order to upload and
dynamically view new projects.</noscript>
<fieldset>
  <p id="status">Select a scratch file</p>
  <div id="progressbar"></div>
  <input id="file" type="file" />
  <div id="drop">or drop file here</div>
</fieldset>
<h3>Uploaded projects (updated in real-time)</h3>
<div id="projects">%s</div>
<script>
  function sse() {
      var source = new EventSource('/stream');
      source.onmessage = function(e) {
          if (e.data == '')
              return;
          var data = $.parseJSON(e.data);
          var upload_message = 'Project uploaded by ' + data['ip_addr'];
          var body = $(data['data']);
          var container = $('<div class="analysis">').hide();
          container.append($('<div>', {text: upload_message}));
          container.append(body);
          $('#projects').prepend(container);
          body.load(function(){
              container.show('blind', {}, 1000);
          });
      };
  }
  function file_select_handler(to_upload) {
      var progressbar = $('#progressbar');
      var status = $('#status');
      var xhr = new XMLHttpRequest();
      xhr.upload.addEventListener('loadstart', function(e1){
          status.text('uploading scratch file');
          progressbar.progressbar({max: e1.total});
      });
      xhr.upload.addEventListener('progress', function(e1){
          if (progressbar.progressbar('option', 'max') == 0)
              progressbar.progressbar('option', 'max', e1.total);
          progressbar.progressbar('value', e1.loaded);
      });
      xhr.onreadystatechange = function(e1) {
          if (this.readyState == 4)  {
              if (this.status == 200)
                  var text = 'upload complete: ' + this.responseText;
              else
                  var text = 'upload failed: code ' + this.status;
              status.html(text + '<br/>Select an a scratch file');
              progressbar.progressbar('destroy');
          }
      };
      xhr.open('POST', '/post', true);
      xhr.send(to_upload);
  };
  function handle_hover(e) {
      e.originalEvent.stopPropagation();
      e.originalEvent.preventDefault();
      e.target.className = (e.type == 'dragleave' || e.type == 'drop') ? '' : 'hover';
  }

  $('#drop').bind('drop', function(e) {
      handle_hover(e);
      if (e.originalEvent.dataTransfer.files.length < 1) {
          return;
      }
      file_select_handler(e.originalEvent.dataTransfer.files[0]);
  }).bind('dragenter dragleave dragover', handle_hover);
  $('#file').change(function(e){
      file_select_handler(e.target.files[0]);
      e.target.value = '';
  });
</script>
""" % (INCLUDES, '\n'.join(scratch_files))
    if PRODUCTION:
        retval += """
<script>
  sse();
  var _gaq = _gaq || [];
  _gaq.push(['_setAccount', 'UA-510348-18']);
  _gaq.push(['_trackPageview']);

  (function() {
    var ga = document.createElement('script'); ga.type = 'text/javascript'; ga.async = true;
    ga.src = ('https:' == document.location.protocol ? 'https://ssl' : 'http://www') + '.google-analytics.com/ga.js';
    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(ga, s);
  })();
</script>
"""
    return retval


if __name__ == '__main__':
    app.debug = True
    app.run('0.0.0.0', threaded=True)
