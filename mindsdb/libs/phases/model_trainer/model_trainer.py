from __future__ import unicode_literals, print_function, division

from mindsdb.config import CONFIG
from mindsdb.libs.constants.mindsdb import *
from mindsdb.libs.phases.base_module import BaseModule
from mindsdb.libs.workers.train import TrainWorker

from mindsdb.libs.data_types.transaction_metadata import TransactionMetadata

import _thread
import time



class ModelTrainer(BaseModule):

    phase_name = PHASE_MODEL_TRAINER



    def run(self):
        """
        Run the training process, we can perhaps iterate over all hyper parameters here and spun off model variations
        TODO: checkout the RISELab distributed ML projects for this

        :return: None
        """

        model_name = self.transaction.persistent_model_metadata.model_name
        train_meta_data = self.transaction.train_metadata # type: TransactionMetadata

        is_time_series = train_meta_data.model_is_time_series

        # choose which models to try
        # NOTE: On server mode more than one can be used, on serverless, choose only
        # TODO: On server mode bring smarter way to choose
        if is_time_series:
            ml_models = [
                ('pytorch.models.ensemble_fully_connected_net', {})
                # ,('pytorch.models.ensemble_conv_net', {})
            ]
        else:
            ml_models = [
                #('pytorch.models.ensemble_conv_net', {})
                ('pytorch.models.fully_connected_buckets_net', {})
                #,('pytorch.models.ensemble_fully_connected_net', {})
            ]


        self.train_start_time = time.time()

        self.session.log.info('Training: model {model_name}, epoch 0'.format(model_name=model_name))

        self.last_time = time.time()
        # We moved everything to a worker so we can run many of these in parallel

        # Train column encoders


        for ml_model_data in ml_models:
            config = ml_model_data[1]
            ml_model = ml_model_data[0]

            if CONFIG.EXEC_LEARN_IN_THREAD == False or len(ml_models) == 1:
                train_worker = TrainWorker.start(self.transaction.model_data, model_name=model_name, ml_model=ml_model, config=config)
                self.transaction.data_model_object = train_worker.train(self.transaction.model_data)
            else:
                # Todo: use Ray https://github.com/ray-project/tutorial
                # Before moving to actual workers: MUST FIND A WAY TO SEND model data to the worker in an efficient way first
                _thread.start_new_thread(TrainWorker.start, (self.transaction.model_data, model_name, ml_model, config))
            # return

        total_time = time.time() - self.train_start_time
        self.session.log.info('Trained: model {model_name} [OK], TOTAL TIME: {total_time:.2f} seconds'.format(model_name = model_name, total_time=total_time))





def test():
    from mindsdb.libs.controllers.mindsdb_controller import Mind as MindsDB

    mdb = MindsDB()
    mdb.learn(
        from_query='''
            select
                id,
                max_time_rec,
                min_time_rec,

                position
            from position_target_table
        ''',
        from_file=CONFIG.MINDSDB_STORAGE_PATH+'/position_target_table.csv',
        group_by='id',
        order_by=['max_time_rec'],
        columns_to_predict='position',
        model_name='mdsb_model',
        breakpoint=PHASE_MODEL_TRAINER
    )


# only run the test if this file is called from debugger
if __name__ == "__main__":
    test()
