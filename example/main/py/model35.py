from typing import NamedTuple
import kfp
from kfp import dsl
from kfp.components import func_to_container_op, InputPath, OutputPath
import kfp.components as components
import datetime
import os

def load_data_func(log_folder:str) -> NamedTuple('Outputs', [('samples', str), ('labels', str)]):
    from typing import NamedTuple
    import os
    import tensorflow as tf
    import numpy as np
    
    # START_DATASET_CODE
    dataset = tf.keras.datasets.mnist
    # END_DATASET_CODE

    (x_train, y_train), (x_test, y_test) = dataset.load_data()
    

    x = np.concatenate((x_train, x_test), axis=0)
    y = np.concatenate((y_train, y_test), axis=0)

    
    
    np.save(os.path.join(log_folder, 'samples.npy'), x)
    np.save(os.path.join(log_folder, 'labels.npy'), y)
    result = NamedTuple('Outputs', [('samples', str), ('labels', str)])
    return result(
        os.path.join(log_folder, 'samples.npy'),
        os.path.join(log_folder, 'labels.npy')
    )

def data_process_func(log_folder:str, samples_path: str, labels_path: str) -> NamedTuple('Outputs', [('x_train', str), ('y_train', str), ('x_test', str), ('y_test', str)]):
    from typing import NamedTuple
    import os
    import tensorflow as tf
    import numpy as np
    from sklearn.model_selection import train_test_split
    import pandas as pd
    from sklearn.preprocessing import LabelEncoder
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.preprocessing import StandardScaler
    from minio import Minio
    from minio.error import S3Error
    import pickle
    from io import BytesIO

    samples = np.load(samples_path)
    labels = np.load(labels_path)
    scaler = False

    
    label_column_name = undefined
    col_names = undefined
    col_names.remove(label_col_name)
    data = pd.DataFrame(samples, columns=col_names[:])  
    data.fillna(value=0, inplace=True)  
    samples = data.values

    
    
    
    x_train, x_test, y_train, y_test = train_test_split(samples, labels, test_size=0.2, random_state=42)

    
    
    scaler = MinMaxScaler(feature_range=(0, 1))
    x_train = x_train.reshape(x_train.shape[0],-1)
    x_test = x_test.reshape(x_test.shape[0],-1)
    x_train = scaler.fit_transform(x_train)
    x_test = scaler.transform(x_test)

    
    x_train = x_train.reshape(x_train.shape[0], -1)
    x_test = x_test.reshape(x_test.shape[0], -1)

    if scaler:
        serialized_scaler = pickle.dumps(scaler)
    
        host = "140.128.102.162:9000"
        username = "pyj93"
        password = "a0909791335"
    
          
        # Initialize MinIO client
        client = Minio(host ,
                    access_key=username,
                    secret_key=password,
                    secure=False)
    
    
        
        bucket_name = "scalers"    
    
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
        try:
            result = client.put_object(bucket_name, 'scaler.pkl', BytesIO(serialized_scaler), len(serialized_scaler))
            print("Uploaded", result.object_name, "with ETag:", result.etag)
        except S3Error as err:
            print("Error:", err)
        
    np.save(os.path.join(log_folder, 'x_train.npy'), x_train)
    np.save(os.path.join(log_folder, 'y_train.npy'), y_train)
    np.save(os.path.join(log_folder, 'x_test.npy'), x_test)
    np.save(os.path.join(log_folder, 'y_test.npy'), y_test)
    result = NamedTuple('Outputs', [('x_train', str), ('y_train', str), ('x_test', str), ('y_test', str)])
    return result(
        os.path.join(log_folder, 'x_train.npy'),
        os.path.join(log_folder, 'y_train.npy'),
        os.path.join(log_folder, 'x_test.npy'),
        os.path.join(log_folder, 'y_test.npy')
    )

def model_func(epochs:int, model_name:str, log_folder:str, x_train_path: str, y_train_path: str, x_test_path: str, y_test_path: str) -> NamedTuple('Outputs', [('logdir', str), ('accuracy', float)]):
    import tensorflow as tf
    import numpy as np
    import datetime
    import json
    import os
    from sklearn.metrics import accuracy_score
    
    import joblib
    print('model_func:', log_folder)
    
    x_train = np.load(x_train_path)
    y_train = np.load(y_train_path)
    x_test = np.load(x_test_path)
    y_test = np.load(y_test_path)
    
   

    def create_model():
        # START_MODEL_CODE
        from sklearn.tree import DecisionTreeClassifier
        return DecisionTreeClassifier(criterion='gini', splitter='best', max_depth=20, min_samples_split=5, min_samples_leaf=5)
        # END_MODEL_CODE

        

        
    model = create_model()
    
    ### add log
    log_dir = os.path.join(log_folder, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    ######
    
    # Train the model
    model.fit(x_train, y_train)
    
    # Get predictions
    y_pred = model.predict(x_test)
    
    # Get accuracy
    accuracy = accuracy_score(y_test, y_pred)
    
    model_path = os.path.join(log_folder, model_name, 'model.joblib') # remove 1
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(model, model_path)
    
    print('logdir:', log_dir)
    print('accuracy', accuracy)
    accuracy = float(accuracy)
    return ([log_dir, accuracy])
def show_results(log_folder:str, accuracy: float) -> NamedTuple('Outputs', [('accuracy', float)]):
    import os

    accuracy_file_path = os.path.join(log_folder, 'accuracy')
    os.makedirs(os.path.dirname(accuracy_file_path), exist_ok=True)
    
    return ([accuracy])
    
def predict_func(model_name: str, log_folder: str) -> NamedTuple('Outputs', [('prediction', str)]):
    import json
    import requests
    import cv2
    import numpy as np
    import pickle
    from minio import Minio
    from minio.error import S3Error
    from io import StringIO, BytesIO
    from kfp_login import get_istio_auth_session
    from retrieve_namespaces import retrieve_namespaces

    host = "http://140.128.102.163:31740"
    username = "kubeflow08@gmail.com"
    password = "bnxm4k"
    
    auth_session = get_istio_auth_session(
        url=host,
        username=username,
        password=password
    )

    configuration = kfp_server_api.Configuration(
        host = os.path.join(host, "pipeline"),
    )
    configuration.debug = True

    namespaces = retrieve_namespaces(host, auth_session)
 
    auth = 'authservice_session={}'.format(auth_session['session_cookie'][20:])
    host = '{}-predictor-default.kubeflow-user-thu10.ai4edu.thu01.footprint-ai.com'.format(model_name)
    predict_url = 'https://ai4edu.thu01.footprint-ai.com/v1/models/{}:predict'.format(model_name)

    min_host = "http://140.128.102.162:9000"
    min_username = "pyj93"
    min_password = "a0909791335"

        
    # Initialize MinIO client
    client = Minio(min_host ,
                access_key=min_username,
                secret_key=min_password ,
                secure=False)

    bucket_name = "sample-bucket"
    object_name = "tiny-4.png"

    try:
        response = client.get_object(bucket_name, object_name)
        

        if "image" != 'image':
            try:
                csvFile = response.read().decode('utf-8')
            except UnicodeDecodeError as ude:
                raise ValueError("Failed to decode the data from MinIO") from ude
                
            data = pd.read_csv(StringIO(csvFile))
            col_names = data.columns.tolist()
            data = data.values
            
        else:
            image_data = response.read()
            numpy_array = np.frombuffer(image_data, np.uint8)
            orig = cv2.imdecode(numpy_array, cv2.IMREAD_GRAYSCALE)
            data = cv2.resize(orig, (28,28,1), interpolation = cv2.INTER_AREA)
            

            
        client.remove_object(bucket_name, object_name)

        scaler = False
        if True:
            response = client.get_object("scaler", 'scaler.pkl')
            scaler_data = response.read()
            scaler = pickle.loads(scaler_data)

            client.remove_object("scaler", "scaler.pkl")
    except S3Error as err:
        print("Error:", err)


    if scaler:
      data = data.reshape(data.shape[0],-1)
      data = scaler.transform(data)  

    data = data.reshape(1, -1)
        


    headers = {'Host': host, 'Cookie': auth}
    classnames = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    payload={"signature_name": "serving_default", "instances": data.tolist()}
    resp = requests.post(predict_url, headers=headers, data=json.dumps(payload))
    resp_json = json.loads(resp.content)
    print('prediction:', resp_json['predictions'][0])
    
    result = NamedTuple('Outputs', [('prediction', str)])
    prediction_value = resp_json['predictions'][0]
    result_instance = result(prediction=prediction_value)

    return result_instance

@dsl.pipeline(
   name='Final pipeline',
   description='A pipeline to train a model on dataset output accuracy.'
)

def decisiontree_pipeline(epochs=5, model_name="model35",):
# END_DEPLOY_CODE
    log_folder = '/data'
    pvc_name = "mypvc"
    vop = dsl.VolumeOp(
        name=pvc_name,
        resource_name="newpvc",
        size="1Gi",
        modes=dsl.VOLUME_MODE_RWO
    )
    
    load_data_op = func_to_container_op(
        func=load_data_func,
        base_image="tensorflow/tensorflow:2.14.0",
        packages_to_install=["minio","pandas"]
    )
    data_process_op = func_to_container_op(
        func=data_process_func,
        base_image="tensorflow/tensorflow:2.14.0",
        packages_to_install=["scikit-learn","pandas","minio"]
    )
    model_op = func_to_container_op(
        func=model_func,
        base_image="tensorflow/tensorflow:2.0.0-py3",
        packages_to_install=["scikit-learn"]
    )
    show_results_op = func_to_container_op(
        func=show_results,
        base_image="tensorflow/tensorflow:2.0.0-py3"
    )
    
    predict_op = func_to_container_op(
        func=predict_func,
        base_image="python:3.7", 
        packages_to_install=["requests","opencv-python-headless", "numpy", "minio"]
    )
    
    
    ########################################################
    load_data_task = load_data_op(log_folder).add_pvolumes({
        log_folder:vop.volume,
    }).set_cpu_limit("1").set_cpu_request("0.5")

    data_process_task = data_process_op(
        log_folder,
        load_data_task.outputs['samples'],
        load_data_task.outputs['labels'],
    ).add_pvolumes({
        log_folder:vop.volume,
    }).set_cpu_limit("1").set_cpu_request("0.5")
    
    model_task = model_op(
        epochs,
        model_name,
        log_folder,
        data_process_task.outputs['x_train'],
        data_process_task.outputs['y_train'],
        data_process_task.outputs['x_test'],
        data_process_task.outputs['y_test'],
    ).add_pvolumes({
        log_folder:vop.volume,
    }).set_cpu_limit("1").set_cpu_request("0.5")

    show_results_task = show_results_op(
        log_folder,
        model_task.outputs['accuracy'],
    ).add_pvolumes({
        log_folder:vop.volume,
    }).set_cpu_limit("1").set_cpu_request("0.5")
    
    predict_task = predict_op(
        model_name,
        log_folder,
    ).add_pvolumes({
        log_folder: vop.volume,
    }).set_cpu_limit("1").set_cpu_request("0.5")
    
pipeline_name='decisiontree_pipeline{}.yaml'.format('model35')
kfp.compiler.Compiler().compile(decisiontree_pipeline, pipeline_name)





import time
import kfp_server_api
import os
import requests
import string
import random
import json
from kfp import dsl
from kfp.components import func_to_container_op, OutputPath
from kfp_server_api.rest import ApiException
from pprint import pprint
from kfp_login import get_istio_auth_session
from kfp_namespace import retrieve_namespaces

host = "http://140.128.102.163:31740"
username = "kubeflow08@gmail.com"
password = "bnxm4k"

auth_session = get_istio_auth_session(
        url=host,
        username=username,
        password=password
    )

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration = kfp_server_api.Configuration(
    host = os.path.join(host, "pipeline"),
)
configuration.debug = True

namespaces = retrieve_namespaces(host, auth_session)
#print("available namespace: {}".format(namespaces))

def random_suffix() :
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

# Enter a context with an instance of the API client
with kfp_server_api.ApiClient(configuration, cookie=auth_session["session_cookie"]) as api_client:
    # Create an instance of the  Experiment API class
    experiment_api_instance = kfp_server_api.ExperimentServiceApi(api_client)
    name="experiment-" + random_suffix()
    description="This is a experiment for only_decisiontree."
    resource_reference_key_id = namespaces[0]
    resource_references=[kfp_server_api.models.ApiResourceReference(
        key=kfp_server_api.models.ApiResourceKey(
            type=kfp_server_api.models.ApiResourceType.NAMESPACE,
            id=resource_reference_key_id
        ),
        relationship=kfp_server_api.models.ApiRelationship.OWNER
    )]
    body = kfp_server_api.ApiExperiment(name=name, description=description, resource_references=resource_references) # ApiExperiment | The experiment to be created.
    try:
        # Creates a new experiment.
        experiment_api_response = experiment_api_instance.create_experiment(body)
        experiment_id = experiment_api_response.id # str | The ID of the run to be retrieved.
    except ApiException as e:
        print("Exception when calling ExperimentServiceApi->create_experiment: %s\n" % e)
    
    # Create an instance of the pipeline API class
    api_instance = kfp_server_api.PipelineUploadServiceApi(api_client) 
    uploadfile=pipeline_name
    name='pipeline-' + random_suffix()
    description="This is a only_decisiontree pipline."
    try:
        pipeline_api_response = api_instance.upload_pipeline(uploadfile, name=name, description=description)
        pipeline_id = pipeline_api_response.id # str | The ID of the run to be retrieved.
    except ApiException as e:
        print("Exception when calling PipelineUploadServiceApi->upload_pipeline: %s\n" % e)

    # Create an instance of the run API class
    run_api_instance = kfp_server_api.RunServiceApi(api_client)
    display_name = 'run_only_decisiontree' + random_suffix()
    description = "This is a only_decisiontree run."
    pipeline_spec = kfp_server_api.ApiPipelineSpec(pipeline_id=pipeline_id)
    resource_reference_key_id = namespaces[0]
    resource_references=[kfp_server_api.models.ApiResourceReference(
    key=kfp_server_api.models.ApiResourceKey(id=experiment_id, type=kfp_server_api.models.ApiResourceType.EXPERIMENT),
    relationship=kfp_server_api.models.ApiRelationship.OWNER )]
    body = kfp_server_api.ApiRun(name=display_name, description=description, pipeline_spec=pipeline_spec, resource_references=resource_references) # ApiRun | 
    try:
        # Creates a new run.
        run_api_response = run_api_instance.create_run(body)
        run_id = run_api_response.run.id # str | The ID of the run to be retrieved.
    except ApiException as e:
        print("Exception when calling RunServiceApi->create_run: %s\n" % e)

    Completed_flag = False
    polling_interval = 10  # Time in seconds between polls

    


    while not Completed_flag:
        try:
            time.sleep(1)
            # Finds a specific run by ID.
            api_instance = run_api_instance.get_run(run_id)
            output = api_instance.pipeline_runtime.workflow_manifest
            output = json.loads(output)
            #print(output)

            try:
                nodes = output['status']['nodes']
                conditions = output['status']['conditions'] # Comfirm completion.
                    
            except KeyError:
                nodes = {}
                conditions = []

            output_value = None
            Completed_flag = conditions[1]['status'] if len(conditions) > 1 else False
            
            '''''
            def find_all_keys(node):
                if isinstance(node, dict):
                    for key in node.keys():
                        print("Key:", key)
                        find_all_keys(node[key])
                elif isinstance(node, list):
                    for item in node:
                        find_all_keys(item)

            # Call the function with your JSON data
            find_all_keys(output)
            '''''

        except ApiException as e:
            print("Exception when calling RunServiceApi->get_run: %s\n" % e)
            break

        if not Completed_flag:
            print("Pipeline is still running. Waiting...")
            time.sleep(polling_interval-1)
    
    found_final_pvc_name = False  # Add a variable to track if the PVC name has been found

    def find_final_pvc_name(node):
        global found_final_pvc_name  # Declare the variable as global

        if not found_final_pvc_name:  # If the PVC name has not been found yet
            if isinstance(node, dict):
                if 'parameters' in node:
                    parameters = node['parameters']
                    for parameter in parameters:
                        if 'name' in parameter and parameter['name'] == 'mypvc-name':
                            value = parameter.get('value')
                            if value and not value.startswith('{{') and not value.endswith('}}'):
                                found_final_pvc_name = True  # Set to True after finding the PVC name
                                print("mypvc-name:", value)
                                return value
                for key, value in node.items():
                    result = find_final_pvc_name(value)
                    if result:
                        return result
            elif isinstance(node, list):
                for item in node:
                    result = find_final_pvc_name(item)
                    if result:
                        return result

        return None
    
    find_final_pvc_name(output)  # Call the function to find final_pvc_name


    found_model_func_accuracy = False

    def find_model_func_accuracy(node):
        global found_model_func_accuracy  # Declare the variable as global

        if not found_model_func_accuracy:  # If the model-func-accuracy has not been found yet
            if isinstance(node, dict):
                if 'parameters' in node:
                    parameters = node['parameters']
                    for parameter in parameters:
                        if 'name' in parameter and parameter['name'] == 'model-func-accuracy':
                            value = parameter.get('value')
                            if value and not value.startswith('{{') and not value.endswith('}}'):
                                found_model_func_accuracy = True  # Set to True after finding model-func-accuracy
                                print("DECISIONTREE Model Accuracy:", value)
                                return value

                for key, value in node.items():
                    result = find_model_func_accuracy(value)
                    if result:
                        return result
            elif isinstance(node, list):
                for item in node:
                    result = find_model_func_accuracy(item)
                    if result:
                        return result

        return None
    
    find_model_func_accuracy(output)
