import codecs
import inspect
import json
import logging
import os
import time
import datetime
from functools import wraps

import jwt
import platform
from dataclasses import asdict
from distutils import util

import yaml
from flask import request, Response, Flask, session, redirect, url_for, render_template, jsonify
from jwt import InvalidTokenError
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash, check_password_hash

import mongo_handler.mongo_utils
from mongo_handler.mongo_objects import UserObject, DeploymentYAMLObject
from variables.variables import POST, GET, EKS, \
    APPLICATION_JSON, CLUSTER_TYPE, GKE, AKS, DELETE, USER_NAME, MACOS, REGIONS_LIST, \
    ZONES_LIST, HELM_INSTALLS_LIST, GKE_VERSIONS_LIST, GKE_IMAGE_TYPES, HELM, LOCATIONS_DICT, \
    CLUSTER_NAME
from cluster_operations import trigger_gke_build_github_action, trigger_eks_build_github_action, \
    trigger_aks_build_github_action, delete_gke_cluster, delete_eks_cluster, delete_aks_cluster, \
    trigger_trolley_agent_deployment_github_action
from utils import random_string, apply_yaml

REGISTRATION = False
CUR_DIR = os.getcwd()
PROJECT_ROOT = "/".join(CUR_DIR.split('/'))

logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
logger = logging.getLogger()

if MACOS in platform.platform():
    log_path = f'{os.getcwd()}'
else:
    log_path = '/var/log/'
file_name = 'server_main.log'
fileHandler = logging.FileHandler("{0}/{1}".format(log_path, file_name))
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
#
# handler = logging.FileHandler('../trolley.log')
# handler.setLevel(logging.DEBUG)
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger.addHandler(handler)

logger.info(f'The current directory is: {CUR_DIR}')
logger.info(f'The content of the directory is: {os.listdir(CUR_DIR)}')

PROJECT_NAME = os.getenv('PROJECT_NAME')

app = Flask(__name__, static_folder='front/build/static', template_folder='front/build')
logger.info(os.getenv('SECRET_KEY'))
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['UPLOAD_FOLDER'] = ''

if MACOS in platform.platform():
    CUR_DIR = os.getcwd()
    PROJECT_ROOT = "/".join(CUR_DIR.split('/'))
    logger.info(f'current directory is: {PROJECT_ROOT}')
else:
    PROJECT_NAME = os.environ['PROJECT_NAME']


def yaml_to_dict(content) -> dict:
    full_deployment_yaml = content['deployment_yaml']
    deployment_yaml_dict = []
    if '---' in full_deployment_yaml:
        deployments_list = full_deployment_yaml.split('---')
        for deployment in deployments_list:
            single_deployment = yaml.safe_load(deployment)
            deployment_yaml_dict.append(single_deployment)
    else:
        deployment_yaml_dict = yaml.safe_load(full_deployment_yaml)
    return deployment_yaml_dict


def deployment_yaml_object_handling(content) -> DeploymentYAMLObject:
    return DeploymentYAMLObject(content['cluster_type'], content['cluster_name'], yaml_to_dict(content))


def user_registration(first_name: str = '', last_name: str = '', password: str = '',
                      user_email: str = '', team_name: str = '', profile_image_filename: str = '') -> bool:
    """
    This function registers a new user into the DB
    """
    user_name = f'{first_name.lower()}{last_name.lower()}'
    hashed_password = generate_password_hash(password, method='sha256')
    profile_image_id = mongo_handler.mongo_utils.insert_file(profile_image_filename)
    user_object = UserObject(first_name=first_name, last_name=last_name, user_name=user_name, user_email=user_email,
                             team_name=team_name, hashed_password=hashed_password, profile_image_id=profile_image_id)
    if mongo_handler.mongo_utils.insert_user(asdict(user_object)):
        if 'trolley' in profile_image_filename:
            return True
        if os.path.exists(profile_image_filename):
            os.remove(profile_image_filename)
        return True
    else:
        return False


def login_processor(user_email: str = "", password: str = "", new: bool = False) -> tuple:
    user_agent = request.headers.get('User-Agent')
    logger.info(f'The request comes from {user_agent} user agent')
    if new:
        session.pop('x-access-token', None)
        session.pop('user_email', None)
        session.pop('user_password', None)
    if not user_email and not password:
        try:
            user_email = session['user_email']
            password = session['user_password']
        except:
            user_email = request.form['user_email']
            password = request.form['user_password']
    logger.info(f'The request is being done with: {user_email} user')
    user_object = mongo_handler.mongo_utils.retrieve_user(user_email)
    logger.info(f'user_obj is: {user_object}')
    if not user_object:
        return '', {'user_email': user_email}
    session['user_email'] = user_email
    session['user_password'] = password
    try:
        session['first_name'] = user_object['first_name'].capitalize()
    except:
        return redirect(url_for('login',
                         failure_message=f'username or password were not found in the system '
                                         f' please try again'))
    if not user_email or not password:
        return redirect(url_for('login',
                               failure_message=f'{user_email} was not found in the system '
                                               f'or you provided a wrong password, please try again'))
    try:
        logger.info(f'checking the password for {user_object}')
        if check_password_hash(user_object['hashed_password'], password):
            logger.info(f'The hashed password is correct')
            try:
                token = jwt.encode(
                    {'user_id': str(user_object['_id']),
                     'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=1440)},
                    app.config['SECRET_KEY'])
            except InvalidTokenError as error:
                logger.error(error)
                logger.info(f'Failed to create a token')
                token = ''
            # decoded_token = token.decode("utf-8")
            session['x-access-token'] = token
            logger.info(f'The decoded token is: {token}')
            return token, user_object
        else:
            logger.info('The hashed password is incorrect')
            logger.info(f'The hashed password is incorrect')
            return '', user_object
    except:
        logger.info(f'The hashed password is incorrect')
        return redirect(url_for('login',
                         failure_message=f'username or password were not found in the system '
                                         f' please try again'))


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            login_processor()
            return f(*args, **kwargs)
        except:
            return False

    return decorated_function


def render_page(page_name: str = ''):
    try:
        token, user_object = login_processor()
        base64_data = codecs.encode(user_object['profile_image'].read(), 'base64')
        is_login_pass = True
    except:
        is_login_pass = False
    if is_login_pass:
        data = {'user_name': user_object['user_name'], 'first_name': user_object['first_name']}
        profile_image = base64_data.decode('utf-8')
        return render_template('index.html', data=data, image=profile_image)
    else:
        return redirect(url_for('login'))


@app.route('/get_clusters_data', methods=[GET])
@login_required
def get_clusters_data():
    """
    Ths endpoint allows providing basic clusters data that was gathered upon the clusters creation.
    """
    cluster_type = request.args.get(CLUSTER_TYPE)
    user_name = request.args.get(USER_NAME.lower())
    clusters_list = mongo_handler.mongo_utils.retrieve_available_clusters(cluster_type, user_name)
    return Response(json.dumps(clusters_list), status=200, mimetype=APPLICATION_JSON)


@app.route('/get_agent_cluster_data', methods=[GET])
@login_required
def get_agent_cluster_data():
    """
    This endpoint allows providing an additional cluster data that is being collected by the deployed Trolley Agent
    """
    cluster_name = request.args.get(CLUSTER_NAME.lower())
    cluster_object = mongo_handler.mongo_utils.retrieve_agent_cluster_details(cluster_name)
    return Response(json.dumps(cluster_object), status=200, mimetype=APPLICATION_JSON)


# @app.route('/trigger_cluster_deployment', methods=[POST])
# def trigger_cluster_deployment():
#     content = request.get_json()
#     function_name = inspect.stack()[0][3]
#     logger.info(f'A request for {function_name} was requested with the following parameters: {content}')
#     user_name = content['user_name']
#     cluster_type = content['cluster_type']
#     cluster_name = f'{user_name}-{cluster_type}-{random_string(8)}'
#     content['cluster_name'] = cluster_name
#     full_deployment_yaml = content['deployment_yaml']
#     deployment_yaml_dict = []
#     if '---' in full_deployment_yaml:
#         deployments_list = full_deployment_yaml.split('---')
#         for deployment in deployments_list:
#             single_deployment = yaml.safe_load(deployment)
#             deployment_yaml_dict.append(single_deployment)
#     else:
#         deployment_yaml_dict = full_deployment_yaml
#     del content['deployment_yaml']
#     if cluster_type == GKE:
#         trigger_gke_build_github_action(**content)
#     elif cluster_type == EKS:
#         trigger_eks_build_github_action(**content)
#     elif cluster_type == AKS:
#         trigger_eks_build_github_action(**content)
#     deployment_yaml_object = DeploymentYAMLObject(cluster_name, deployment_yaml_dict)
#     if mongo_handler.mongo_utils.x_deployment_yaml(asdict(deployment_yaml_object)):
#         return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)
#     else:
#         return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)

@app.route('/deploy_yaml_on_cluster', methods=[POST])
@login_required
def deploy_yaml_on_cluster():
    """
    This endpoint allows delivering a custom deployment using a YAML that was provided for a cluster
    """
    content = request.get_json()
    function_name = inspect.stack()[0][3]
    with open('trolley_service.yaml', "r") as f:
        yaml_content = f.read().strip()
    deployment_yaml = yaml.safe_load(yaml_content)
    logger.info(f'A request for {function_name} was requested with the following parameters: {content}')
    if apply_yaml(content[CLUSTER_TYPE], content[CLUSTER_NAME.lower()], deployment_yaml):
        return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)


@app.route('/deploy_trolley_agent_on_cluster', methods=[POST])
@login_required
def deploy_trolley_agent_on_cluster():
    """
    This endpoint allows triggering a Trolley Agent deployment on a cluster
    """
    content = request.get_json()
    function_name = inspect.stack()[0][3]
    logger.info(f'A request for {function_name} was requested with the following parameters: {content}')
    if trigger_trolley_agent_deployment_github_action(**content):
        return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)


@app.route('/trigger_gke_deployment', methods=[POST])
@login_required
def trigger_gke_deployment():
    """
    This endpoint triggers a GKE Cluster deployment
    """
    content = request.get_json()
    function_name = inspect.stack()[0][3]
    logger.info(f'A request for {function_name} was requested with the following parameters: {content}')
    user_name = content['user_name']
    cluster_name = f'{user_name}-{GKE}-{random_string(8)}'
    content['cluster_name'] = cluster_name
    if trigger_gke_build_github_action(**content):
        deployment_yaml_object = deployment_yaml_object_handling(content)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)
    if mongo_handler.mongo_utils.insert_deployment_yaml(asdict(deployment_yaml_object)):
        return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)


@app.route('/trigger_eks_deployment', methods=[POST])
@login_required
def trigger_eks_deployment():
    """
    This endpoint triggers an EKS Cluster deployment
    """
    content = request.get_json()
    function_name = inspect.stack()[0][3]
    logger.info(f'A request for {function_name} was requested with the following parameters: {content}')
    user_name = content['user_name']
    cluster_name = f'{user_name}-{EKS}-{random_string(8)}'
    content['cluster_name'] = cluster_name
    if trigger_eks_build_github_action(**content):
        deployment_yaml_object = deployment_yaml_object_handling(content)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)
    if mongo_handler.mongo_utils.insert_deployment_yaml(asdict(deployment_yaml_object)):
        return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)


@app.route('/trigger_aks_deployment', methods=[POST])
@login_required
def trigger_aks_deployment():
    """
    This endpoint allows an AKS Cluster deployment
    """
    content = request.get_json()
    function_name = inspect.stack()[0][3]
    logger.info(f'A request for {function_name} was requested with the following parameters: {content}')
    user_name = content['user_name']
    cluster_name = f'{user_name}-{AKS}-{random_string(8)}'
    content['cluster_name'] = cluster_name
    if trigger_aks_build_github_action(**content):
        deployment_yaml_object = deployment_yaml_object_handling(content)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)
    if mongo_handler.mongo_utils.insert_deployment_yaml(asdict(deployment_yaml_object)):
        return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)


@app.route('/delete_expired_clusters', methods=[DELETE])
@login_required
def delete_expired_clusters():
    """
    Ths endpoint allows deletion of clusters that passed their expiration time
    """
    content = request.get_json()
    expired_clusters_list = mongo_handler.mongo_utils.retrieve_expired_clusters(cluster_type=content['cluster_type'])
    for expired_cluster in expired_clusters_list:
        delete_gke_cluster(cluster_name=expired_cluster['cluster_name'])
        time.sleep(5)
        mongo_handler.mongo_utils.set_cluster_availability(cluster_type=content['cluster_type'],
                                                           cluster_name=content['cluster_name'],
                                                           availability=False)
    return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)


@app.route('/delete_cluster', methods=[DELETE])
@login_required
def delete_cluster():
    """
    This request deletes a selected cluster
    """
    content = request.get_json()
    function_name = inspect.stack()[0][3]
    logger.info(f'A request for {function_name} was requested with the following parameters: {content}')
    if content[CLUSTER_TYPE] == GKE:
        del content[CLUSTER_TYPE]
        delete_gke_cluster(**content)
        mongo_handler.mongo_utils.set_cluster_availability(cluster_type=GKE,
                                                           cluster_name=content['cluster_name'],
                                                           availability=False)
    elif content[CLUSTER_TYPE] == EKS:
        del content[CLUSTER_TYPE]
        delete_eks_cluster(**content)
        mongo_handler.mongo_utils.set_cluster_availability(cluster_type=EKS,
                                                           cluster_name=content['cluster_name'],
                                                           availability=False)
    elif content[CLUSTER_TYPE] == AKS:
        del content[CLUSTER_TYPE]
        delete_aks_cluster(**content)
        mongo_handler.mongo_utils.set_cluster_availability(cluster_type=AKS,
                                                           cluster_name=content['cluster_name'],
                                                           availability=False)
    return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)


@app.route('/insert_agent_data', methods=[POST])
@login_required
def insert_agent_data():
    """
    This endpoint inserts data provided by a Trolley Agent
    """
    content = request.get_json()
    function_name = inspect.stack()[0][3]
    logger.info(f'A request for {function_name} was requested')
    if mongo_handler.mongo_utils.insert_agents_data_object(content):
        return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)
    else:
        return Response(json.dumps('Failure'), status=400, mimetype=APPLICATION_JSON)


@app.route('/healthz', methods=[GET, POST])
def healthz():
    logger.info('A request was received')
    return Response(json.dumps('OK'), status=200, mimetype=APPLICATION_JSON)


@app.route('/', methods=[GET, POST])
def root():
    return render_page('index.html')


@app.route('/index', methods=[GET, POST])
def index():
    return render_page('index.html')


@app.route('/fetch_regions', methods=[GET])
@login_required
def fetch_regions():
    cluster_type = request.args.get("cluster_type")
    logger.info(f'A request to fetch regions for {cluster_type} has arrived')
    if cluster_type == AKS:
        regions = mongo_handler.mongo_utils.retrieve_cache(cache_type=LOCATIONS_DICT, provider=AKS)
    elif cluster_type == GKE:
        regions = mongo_handler.mongo_utils.retrieve_cache(cache_type=REGIONS_LIST, provider=GKE)
    elif cluster_type == EKS:
        regions = mongo_handler.mongo_utils.retrieve_cache(cache_type=REGIONS_LIST, provider=EKS)
    else:
        regions = mongo_handler.mongo_utils.retrieve_cache(cache_type=REGIONS_LIST, provider=GKE)
    return jsonify(regions)


@app.route('/fetch_zones', methods=[GET])
@login_required
def fetch_zones():
    cluster_type = request.args.get("cluster_type")
    region_name = request.args.get("region_name")
    logger.info(f'A request to fetch zones for {cluster_type} has arrived')
    zones_list = []
    if cluster_type == AKS:
        return jsonify('')
    elif cluster_type == GKE:
        gke_zones = mongo_handler.mongo_utils.retrieve_cache(cache_type=ZONES_LIST, provider=GKE)
        for zone in gke_zones:
            if region_name in zone:
                zones_list.append(zone)
        return jsonify(zones_list)
    elif cluster_type == EKS:
        eks_zones = mongo_handler.mongo_utils.retrieve_cache(cache_type=ZONES_LIST, provider=EKS)
        available_eks_zones = []
        for eks_zone in eks_zones:
            if region_name in eks_zone:
                available_eks_zones.append(eks_zone)
        return jsonify(available_eks_zones)


@app.route('/fetch_subnets', methods=[GET])
@login_required
def fetch_subnets():
    cluster_type = request.args.get("cluster_type")
    zone_names = request.args.get("zone_names")
    logger.info(f'A request to fetch zone_names for {cluster_type} has arrived')
    if cluster_type == AKS:
        return jsonify('')
    elif cluster_type == GKE:
        return jsonify('')
    elif cluster_type == EKS:
        subnets = []
        subnets_dict = mongo_handler.mongo_utils.retrieve_cache(cache_type='subnets_dict', provider=EKS)
        for subnet in subnets_dict:
            if subnet in zone_names:
                subnets.append(subnets_dict[subnet])
        if len(subnets[0]) < 1:
            return jsonify([f'No subnets were found for {zone_names} zones'])
        else:
            return jsonify(subnets)


@app.route('/fetch_helm_installs', methods=[GET, POST])
@login_required
def fetch_helm_installs():
    names = bool(util.strtobool(request.args.get("names")))
    logger.info(f'A request to fetch helm installs for {names} names has arrived')
    helm_installs_list = mongo_handler.mongo_utils.retrieve_cache(cache_type=HELM_INSTALLS_LIST, provider=HELM)
    return jsonify(helm_installs_list)


@app.route('/fetch_gke_versions', methods=[GET])
@login_required
def fetch_gke_versions():
    gke_versions_list = mongo_handler.mongo_utils.retrieve_cache(cache_type=GKE_VERSIONS_LIST, provider=GKE)
    return jsonify(gke_versions_list)


@app.route('/fetch_gke_image_types', methods=[GET])
@login_required
def fetch_gke_image_types():
    logger.info(f'A request to fetch available GKE image types has arrived')
    gke_image_types_list = mongo_handler.mongo_utils.retrieve_cache(cache_type=GKE_IMAGE_TYPES, provider=GKE)
    return jsonify(gke_image_types_list)


@app.route('/register', methods=[GET, POST])
@login_required
def register():
    if request.method == 'GET':
        return render_template('index.html')
    if request.method == 'POST':
        first_name = request.form['first_name'].lower()
        last_name = request.form['last_name'].lower()
        user_email = request.form['user_email']
        team_name = request.form['team_name']
        password = request.form['password']
        if 'image' not in request.files['file'].mimetype:
            file_path = 'trolley_small.png'
        else:
            profile_image = request.files['file']
            image_extension = profile_image.mimetype.split('/')[1]
            file_path = f'{first_name}{last_name}.{image_extension}'
            FileStorage(profile_image.save(os.path.join(app.config['UPLOAD_FOLDER'], file_path)))

        if not REGISTRATION:
            return redirect(url_for('login',
                                   failure_message='Registration is closed at the moment'))
        if not first_name:
            return render_template('index.html',
                                   error_message=f'Dear {first_name}, your first name was not entered correctly. '
                                                 f'Please try again')
        if not last_name:
            return render_template('index.html',
                                   error_message=f'Dear {first_name}, your last name was not entered correctly. '
                                                 f'Please try again')
        if not first_name:
            return render_template('index.html',
                                   error_message=f'Your first name was not entered correctly. Please try again')
        if not password:
            return render_template('index.html',
                                   error_message=f'Dear {first_name}, your password was not entered correctly. '
                                                 f'Please try again')
        else:
            if not mongo_handler.mongo_utils.retrieve_user(user_email):
                if user_registration(first_name, last_name, password, user_email, team_name, file_path):
                    return redirect(url_for('login',
                                           failure_message=f'Dear {first_name.capitalize()}, '
                                                         f'Welcome to {PROJECT_NAME.capitalize()}!'))
                else:
                    return redirect(url_for('login',
                                           failure_message=f'Dear {first_name.capitalize()}, '
                                                         f'your password was not entered correctly. '
                                                         f'Please try again'))
            else:
                return render_template('index.html',
                                       error_message=f'Dear {first_name}, your email was already registered. '
                                                     f'Please try again')


@app.route('/login', methods=[GET, POST])
@login_required
def login():
    message = request.args.get('failure_message')
    if message is None:
        message = ''
    if request.method == 'GET':
        return render_template('index.html', failure_message=message)
    if request.method == 'POST':
        token, user_object = login_processor(new=True)
        base64_data = codecs.encode(user_object['profile_image'].read(), 'base64')
        profile_image = base64_data.decode('utf-8')
        if token:
            data = {'user_name': user_object['user_name'], 'first_name': user_object['first_name']}
            return redirect(url_for('root', data=data, image=profile_image))
        else:
            user_email = user_object['user_email']
            return render_template('index.html',
                                   failure_message=f'Dear {user_email}, your password was not entered correctly. '
                                                 f'Please try again')


@app.route('/build-eks-clusters', methods=[GET, POST])
def build_eks_clusters():
    return render_page('build-eks-clusters.html')


@app.route('/build-aks-clusters', methods=[GET, POST])
def build_aks_clusters():
    return render_page('build-aks-clusters.html')


@app.route('/build-gke-clusters', methods=[GET, POST])
def build_gke_clusters():
    return render_page('build-gke-clusters.html')


@app.route('/manage-eks-clusters', methods=[GET, POST])
def manage_eks_clusters():
    return render_page('manage-eks-clusters.html')


@app.route('/manage-aks-clusters', methods=[GET, POST])
def manage_aks_clusters():
    return render_page('manage-aks-clusters.html')


@app.route('/manage-gke-clusters', methods=[GET, POST])
def manage_gke_clusters():
    return render_page('manage-gke-clusters.html')


@app.route('/logout', methods=[GET, POST])
def logout():
    session.pop('x-access-token', None)
    session.pop('user_email', None)
    session.pop('user_password', None)
    return redirect(url_for('login'))


app.run(host='0.0.0.0', port=8081, debug=True)
# web.run(host='0.0.0.0', port=8081, debug=True, ssl_context=('certs/cert.pem', 'certs/key.pem'))
